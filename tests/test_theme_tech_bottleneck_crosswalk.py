from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from stock_research.theme_tech_bottleneck_crosswalk import (
    TECH_BOTTLENECK_CROSSWALK_DIR,
    ThemeTechBottleneckCrosswalkValidationError,
    cli,
    existing_evidence_id,
    existing_source_id,
    load_company_crosswalk_details,
    load_theme_crosswalk_details,
    load_theme_tech_bottleneck_crosswalk_package,
    summarize_theme_tech_bottleneck_crosswalk_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_DIR = Path(
    "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1"
)
INPUT_FILES = (
    "tech_bottleneck_review_universe_frontend_dataset.csv",
    "tech_bottleneck_review_universe_frontend_evidence_index.csv",
    "tech_bottleneck_review_universe_frontend_source_index.csv",
)


def test_ai_power_crosswalk_package_loads_and_summarizes_without_writes():
    before = _input_hashes(REPOSITORY_ROOT)

    package = load_theme_tech_bottleneck_crosswalk_package()
    summary = summarize_theme_tech_bottleneck_crosswalk_package(package)

    assert _input_hashes(REPOSITORY_ROOT) == before
    assert summary == {
        "accounted_mapping_count": 4,
        "artifact_count": 1,
        "coverage_gap_count": 2,
        "crosswalk_count": 2,
        "existing_evidence_count": 3,
        "linked_company_count": 2,
        "mapping_coverage_rate": 1.0,
        "new_theme_evidence_count": 4,
        "p4_mapping_count": 4,
        "theme_count": 1,
        "universe_count": 378,
    }
    assert len(package["indexes"]["existing_evidence_by_id"]) == len(
        package["existing_evidence_rows"]
    )
    assert len(package["indexes"]["existing_source_by_id"]) == len(
        package["existing_source_rows"]
    )


@pytest.mark.parametrize(
    ("company_code", "node_id", "stock_name"),
    [
        ("002837.SZ", "liquid_cooling", "英维克"),
        ("002335.SZ", "ups", "科华数据"),
    ],
)
def test_linked_company_detail_resolves_both_evidence_systems(
    company_code: str, node_id: str, stock_name: str
):
    details = load_company_crosswalk_details(company_code)

    assert len(details) == 1
    detail = details[0]
    assert detail["status"] == "linked"
    assert detail["crosswalk_review_status"] == "reviewed"
    assert "review_status" not in detail
    assert detail["theme_node_id"] == node_id
    assert detail["existing_review_universe"]["stock_name"] == stock_name
    assert detail["existing_review_universe"]["used_for_signal"] == "False"
    assert detail["existing_review_universe"]["used_for_admission"] == "False"
    assert detail["existing_review_universe"]["auto_added_to_quality_pool"] == "False"
    assert detail["theme_company_mapping"]["company_code"] == company_code
    assert detail["theme_company_mapping"]["mapped_node_id"] == node_id
    assert detail["existing_evidence"]
    assert all(row["stock_code"] == company_code.split(".")[0] for row in detail["existing_evidence"])
    assert all(row["existing_source"] for row in detail["existing_evidence"])
    assert detail["new_theme_evidence"]
    assert all(row["source"]["review_status"] == "accepted" for row in detail["new_theme_evidence"])


@pytest.mark.parametrize(
    ("company_code", "node_id"),
    [
        ("300870.SZ", "server_power_supply"),
        ("002364.SZ", "hvdc_power"),
    ],
)
def test_missing_universe_companies_are_explicit_coverage_gaps(
    company_code: str, node_id: str
):
    details = load_company_crosswalk_details(company_code)

    assert details == [
        {
            **details[0],
            "status": "coverage_gap",
            "reason": "company_not_in_existing_review_universe",
            "company_code": company_code,
            "theme_node_id": node_id,
        }
    ]
    assert details[0]["existing_review_universe"] is None
    assert details[0]["new_theme_evidence"]


def test_theme_detail_accounts_for_every_phase4_mapping():
    details = load_theme_crosswalk_details("ai_power_value_capture_v1")

    assert len(details) == 4
    assert {row["status"] for row in details} == {"linked", "coverage_gap"}
    assert {row["company_code"] for row in details} == {
        "002335.SZ",
        "002364.SZ",
        "002837.SZ",
        "300870.SZ",
    }


def test_crosswalk_rejects_missing_phase4_mapping(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0]["mapping_id"] = "missing_mapping"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "CROSSWALK_REFERENCES_MISSING_MAPPING"


def test_crosswalk_rejects_existing_evidence_from_another_company(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0]["existing_evidence_ids"] = payload["crosswalks"][1][
        "existing_evidence_ids"
    ]
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "CROSSWALK_EXISTING_EVIDENCE_SCOPE_MISMATCH"


def test_reviewed_crosswalk_requires_confidence(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0]["confidence"] = 0.69
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "REVIEWED_CROSSWALK_REQUIRES_CONFIDENCE"


@pytest.mark.parametrize(
    ("field", "error_code"),
    [
        ("existing_evidence_ids", "CROSSWALK_REQUIRES_EXISTING_EVIDENCE"),
        ("new_theme_evidence_ids", "CROSSWALK_REQUIRES_NEW_THEME_EVIDENCE"),
    ],
)
def test_reviewed_crosswalk_requires_evidence_on_both_sides(
    tmp_path: Path, field: str, error_code: str
):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0][field] = []
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == error_code


def test_present_company_cannot_be_recorded_as_coverage_gap(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    linked = payload["crosswalks"].pop(0)
    payload["coverage_gaps"].append(
        {
            "gap_id": "invalid_present_company_gap",
            "theme_id": linked["theme_id"],
            "theme_node_id": linked["theme_node_id"],
            "company_code": linked["company_code"],
            "company_name": linked["company_name"],
            "mapping_id": linked["mapping_id"],
            "new_theme_evidence_ids": linked["new_theme_evidence_ids"],
            "reason": "company_not_in_existing_review_universe",
            "notes": "Invalid fixture.",
        }
    )
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "COVERAGE_GAP_COMPANY_PRESENT"


def test_phase4_mapping_cannot_be_covered_twice(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    duplicate = dict(payload["coverage_gaps"][0])
    duplicate["gap_id"] = "duplicate_gap"
    payload["coverage_gaps"].append(duplicate)
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "DUPLICATE_MAPPING_COVERAGE"


def test_input_snapshot_digest_detects_upstream_drift(tmp_path: Path):
    repository_root = _copy_universe_inputs(tmp_path)
    dataset_path = repository_root / UNIVERSE_DIR / INPUT_FILES[0]
    dataset_path.write_text(dataset_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    error = _load_invalid_package(
        TECH_BOTTLENECK_CROSSWALK_DIR,
        repository_root=repository_root,
    )

    assert error.code == "INPUT_SNAPSHOT_DIGEST_MISMATCH"


def test_expected_universe_count_is_enforced(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["universe_snapshot"]["expected_universe_count"] = 379
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "UNIVERSE_COUNT_MISMATCH"


def test_snapshot_paths_must_be_authoritative(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["universe_snapshot"]["dataset_path"] = (
        "outputs/research/other_dataset.csv"
    )
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "NON_AUTHORITATIVE_CROSSWALK_INPUT_PATH"


def test_authoritative_csv_schema_is_required(tmp_path: Path):
    repository_root = _copy_universe_inputs(tmp_path)
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    dataset_path = repository_root / UNIVERSE_DIR / INPUT_FILES[0]
    dataset_path.write_text(
        "stock_code\n" + "\n".join(f"{value:06d}" for value in range(378)) + "\n",
        encoding="utf-8",
    )
    for name in INPUT_FILES[1:]:
        (repository_root / UNIVERSE_DIR / name).write_text(
            "junk\ninvalid\n",
            encoding="utf-8",
        )
    artifact_path = _only_artifact(artifact_dir)
    payload = _read_json(artifact_path)
    _refresh_snapshot_digests(payload, repository_root)
    _write_json(artifact_path, payload)

    error = _load_invalid_package(
        artifact_dir,
        repository_root=repository_root,
    )

    assert error.code == "MISSING_CSV_COLUMNS"


@pytest.mark.parametrize("field", ["frontend_review_status", "admission_status"])
def test_crosswalk_schema_rejects_unknown_status_fields(
    tmp_path: Path, field: str
):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0][field] = "approved"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "UNEXPECTED_FIELD"


def test_crosswalk_company_exchange_must_match_phase4_mapping(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0]["company_code"] = "002837.US"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "CROSSWALK_COMPANY_MISMATCH"


def test_company_lookup_with_wrong_exchange_does_not_match():
    with pytest.raises(ThemeTechBottleneckCrosswalkValidationError) as exc_info:
        load_company_crosswalk_details("002837.US")

    assert exc_info.value.code == "COMPANY_CROSSWALK_NOT_FOUND"


def test_crosswalk_company_name_must_match_both_systems(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0]["company_name"] = "错误公司名"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "CROSSWALK_COMPANY_NAME_MISMATCH"


def test_missing_phase4_mapping_coverage_is_rejected(tmp_path: Path):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["coverage_gaps"].pop()
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INCOMPLETE_PHASE4_MAPPING_COVERAGE"


def test_stable_ids_ignore_checkout_prefix():
    evidence = {
        "stock_code": "002837",
        "source_file": "/Users/first/stock_research/outputs/research/source/report.pdf",
        "page": "9",
        "evidence_claim_type": "hard_tech_exposure",
        "evidence_text": "same evidence",
    }
    source = {
        "stock_code": "002837",
        "source_file": evidence["source_file"],
        "source_type": "annual_report",
        "source_title": "2025年年度报告",
    }
    moved_evidence = {
        **evidence,
        "source_file": "/srv/second/stock_research/outputs/research/source/report.pdf",
    }
    moved_source = {**source, "source_file": moved_evidence["source_file"]}

    assert existing_evidence_id(evidence) == existing_evidence_id(moved_evidence)
    assert existing_source_id(source) == existing_source_id(moved_source)


def test_duplicate_source_key_is_rejected(tmp_path: Path):
    repository_root = _copy_universe_inputs(tmp_path)
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    source_path = repository_root / UNIVERSE_DIR / INPUT_FILES[2]
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    duplicate = dict(rows[0])
    duplicate["source_title"] = f"{duplicate['source_title']} duplicate metadata"
    rows.append(duplicate)
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    artifact_path = _only_artifact(artifact_dir)
    payload = _read_json(artifact_path)
    _refresh_snapshot_digests(payload, repository_root)
    _write_json(artifact_path, payload)

    error = _load_invalid_package(
        artifact_dir,
        repository_root=repository_root,
    )

    assert error.code == "DUPLICATE_EXISTING_SOURCE_KEY"


@pytest.mark.parametrize(
    "field",
    [
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
        "reviewer_decision",
    ],
)
def test_crosswalk_rejects_forbidden_decision_fields(tmp_path: Path, field: str):
    artifact_dir = _copy_crosswalk_artifacts(tmp_path)
    path = _only_artifact(artifact_dir)
    payload = _read_json(path)
    payload["crosswalks"][0][field] = True if field != "reviewer_decision" else "keep"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "FORBIDDEN_CROSSWALK_FIELD"


def test_cli_commands_emit_structured_json(capsys):
    assert cli(["validate"]) == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["status"] == "ok"
    assert validate_payload["crosswalk_count"] == 2

    assert cli(["summary"]) == 0
    summary_payload = json.loads(capsys.readouterr().out)
    assert summary_payload["coverage_gap_count"] == 2

    assert cli(["show-theme", "--theme-id", "ai_power_value_capture_v1"]) == 0
    theme_payload = json.loads(capsys.readouterr().out)
    assert len(theme_payload) == 4

    assert cli(["show-company", "--company-code", "002837.SZ"]) == 0
    company_payload = json.loads(capsys.readouterr().out)
    assert company_payload[0]["status"] == "linked"

    assert cli(["coverage-gaps"]) == 0
    gap_payload = json.loads(capsys.readouterr().out)
    assert len(gap_payload) == 2


def _copy_crosswalk_artifacts(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "crosswalks"
    artifact_dir.mkdir()
    for path in TECH_BOTTLENECK_CROSSWALK_DIR.glob("*.json"):
        _write_json(artifact_dir / path.name, _read_json(path))
    return artifact_dir


def _copy_universe_inputs(tmp_path: Path) -> Path:
    repository_root = tmp_path / "repository"
    target_dir = repository_root / UNIVERSE_DIR
    target_dir.mkdir(parents=True)
    for name in INPUT_FILES:
        shutil.copy2(REPOSITORY_ROOT / UNIVERSE_DIR / name, target_dir / name)
    return repository_root


def _input_hashes(repository_root: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((repository_root / UNIVERSE_DIR / name).read_bytes()).hexdigest()
        for name in INPUT_FILES
    }


def _refresh_snapshot_digests(payload: dict, repository_root: Path) -> None:
    snapshot = payload["universe_snapshot"]
    for path_field, digest_field in (
        ("dataset_path", "dataset_sha256"),
        ("evidence_index_path", "evidence_index_sha256"),
        ("source_index_path", "source_index_sha256"),
    ):
        snapshot[digest_field] = hashlib.sha256(
            (repository_root / snapshot[path_field]).read_bytes()
        ).hexdigest()


def _only_artifact(artifact_dir: Path) -> Path:
    paths = sorted(artifact_dir.glob("*.json"))
    assert len(paths) == 1
    return paths[0]


def _load_invalid_package(
    artifact_dir: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> ThemeTechBottleneckCrosswalkValidationError:
    with pytest.raises(ThemeTechBottleneckCrosswalkValidationError) as exc_info:
        load_theme_tech_bottleneck_crosswalk_package(
            artifact_dir=artifact_dir,
            repository_root=repository_root,
        )
    return exc_info.value


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
