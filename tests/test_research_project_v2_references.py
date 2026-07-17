from copy import deepcopy
import json

import pytest

import stock_research.research_project_v2.references as references_module
from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.references import (
    RESOLVERS,
    ResolvedReference,
    audit_references,
    reference_payload,
    resolve_industry_catalog_v1,
    resolve_json_pointer,
    resolve_theme_research_v1,
)


def _reference(
    *,
    reference_id="ref-1",
    namespace="theme_research_v1",
    object_type="v1_theme",
    object_id="ai_compute_infrastructure_value_chain_v1",
    role="background",
    version=None,
    content_hash=None,
    hash_scope="entire_object",
    hash_fields=None,
):
    reference = {
        "reference_id": reference_id,
        "reference_namespace": namespace,
        "reference_type": object_type,
        "reference_object_id": object_id,
        "reference_role": role,
        "reference_version": version,
        "reference_content_hash": content_hash,
        "hash_scope": hash_scope,
    }
    if hash_fields is not None:
        reference["hash_fields"] = hash_fields
    return reference


def _version(*references):
    return {
        "version_id": "version-1",
        "snapshot": {"references": list(references)},
    }


def _audit_with_temp_theme_artifact(monkeypatch, tmp_path, artifact):
    theme_dir = tmp_path / "theme_decomposition"
    mapping_dir = theme_dir / "company_mappings"
    mapping_dir.mkdir(parents=True)
    artifact_path = theme_dir / "theme.json"
    if isinstance(artifact, bytes):
        artifact_path.write_bytes(artifact)
    else:
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    references_module._theme_index.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(references_module, "THEME_ARTIFACT_DIR", theme_dir)
            patch.setattr(references_module, "COMPANY_MAPPING_DIR", mapping_dir)
            return audit_references(_version(_reference(object_id="theme-1")))
    finally:
        references_module._theme_index.cache_clear()


def test_real_theme_entire_object_audits_as_resolved():
    resolved = resolve_theme_research_v1(
        _reference(version=None, content_hash=None)
    )
    assert resolved is not None
    reference = _reference(
        version=resolved.version,
        content_hash=content_sha256(resolved.payload),
    )

    assert audit_references(_version(reference)) == {
        "status": "pass",
        "total": 1,
        "resolved": 1,
        "issues": [],
    }


def test_audit_reads_snapshot_references_and_ignores_top_level_decoy():
    resolved = resolve_theme_research_v1(_reference())
    assert resolved is not None
    real_reference = _reference(
        version=resolved.version,
        content_hash=content_sha256(resolved.payload),
    )
    version = _version(real_reference)
    version["references"] = [
        _reference(reference_id="decoy", object_id="missing-theme")
    ]

    assert audit_references(version) == {
        "status": "pass",
        "total": 1,
        "resolved": 1,
        "issues": [],
    }


@pytest.mark.parametrize(
    ("resolver", "namespace", "object_type", "object_id"),
    [
        (
            resolve_theme_research_v1,
            "theme_research_v1",
            "v1_theme_node",
            "compute_accelerators_boards",
        ),
        (
            resolve_theme_research_v1,
            "theme_research_v1",
            "v1_source",
            "ai_compute_000977_filing",
        ),
        (
            resolve_theme_research_v1,
            "theme_research_v1",
            "v1_claim",
            "ai_compute_claim_01",
        ),
        (
            resolve_theme_research_v1,
            "theme_research_v1",
            "v1_company_mapping",
            "ai_compute_000977_ai_servers_racks_v1",
        ),
        (
            resolve_industry_catalog_v1,
            "industry_catalog_v1",
            "industry_catalog_chain",
            "ai_compute_infrastructure",
        ),
        (
            resolve_industry_catalog_v1,
            "industry_catalog_v1",
            "industry_catalog_node",
            "ai_compute_accelerators_boards",
        ),
    ],
)
def test_real_v1_object_types_resolve_with_type_and_version(
    resolver, namespace, object_type, object_id
):
    resolved = resolver(
        _reference(
            namespace=namespace,
            object_type=object_type,
            object_id=object_id,
        )
    )

    assert resolved is not None
    assert resolved.namespace == namespace
    assert resolved.object_type == object_type
    assert resolved.object_id == object_id
    assert resolved.version
    assert isinstance(resolved.payload, dict)


def test_selected_fields_requires_non_empty_hash_fields():
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        reference_payload(
            {"theme_id": "theme-1"},
            _reference(hash_scope="selected_fields"),
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_REFERENCE_HASH_FIELDS_REQUIRED"


def test_selected_fields_hash_audits_as_resolved():
    resolved = resolve_theme_research_v1(_reference())
    assert resolved is not None
    selected = {"/theme_id": resolved.payload["theme_id"]}
    reference = _reference(
        version=resolved.version,
        content_hash=content_sha256(selected),
        hash_scope="selected_fields",
        hash_fields=["/theme_id"],
    )

    assert audit_references(_version(reference))["status"] == "pass"


def test_invalid_selected_field_pointer_is_unresolvable():
    reference = _reference(
        content_hash="0" * 64,
        hash_scope="selected_fields",
        hash_fields=["/does-not-exist"],
    )

    result = audit_references(_version(reference))

    assert result["issues"] == [
        {
            "reference_id": "ref-1",
            "status": "unresolvable",
            "error_code": "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE",
        }
    ]


def test_selected_field_pointer_is_not_evaluated_without_expected_hash():
    reference = _reference(
        hash_scope="selected_fields",
        hash_fields=["/does-not-exist"],
    )

    assert audit_references(_version(reference))["status"] == "pass"


@pytest.mark.parametrize(
    ("file_name", "contents", "reason"),
    [
        ("missing.json", None, "FileNotFoundError"),
        ("unicode.json", b"\xff", "UnicodeDecodeError"),
        ("invalid.json", b"{invalid", "JSONDecodeError"),
    ],
)
def test_read_json_wraps_file_decode_and_json_errors(tmp_path, file_name, contents, reason):
    path = tmp_path / file_name
    if contents is not None:
        path.write_bytes(contents)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        references_module._read_json(path)

    assert exc_info.value.code == "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE"
    assert exc_info.value.details == {"path": str(path), "reason": reason}


def test_bad_theme_json_audits_unresolvable_without_polluting_cache(
    monkeypatch, tmp_path
):
    result = _audit_with_temp_theme_artifact(monkeypatch, tmp_path, b"{invalid")

    assert result["issues"][0]["status"] == "unresolvable"
    assert resolve_theme_research_v1(_reference()) is not None


def test_theme_artifact_missing_version_audits_unresolvable(monkeypatch, tmp_path):
    artifact = {
        "theme": {"theme_id": "theme-1"},
        "nodes": [],
        "sources": [],
        "claims": [],
    }

    result = _audit_with_temp_theme_artifact(monkeypatch, tmp_path, artifact)

    assert result["issues"][0]["status"] == "unresolvable"


@pytest.mark.parametrize(
    "nodes",
    [
        {},
        [None],
        [{"node_id": 1}],
    ],
)
def test_theme_artifact_invalid_collection_or_entry_audits_unresolvable(
    monkeypatch, tmp_path, nodes
):
    artifact = {
        "artifact_version": "theme-v1",
        "theme": {"theme_id": "theme-1"},
        "nodes": nodes,
        "sources": [],
        "claims": [],
    }

    result = _audit_with_temp_theme_artifact(monkeypatch, tmp_path, artifact)

    assert result["issues"][0]["status"] == "unresolvable"


def test_catalog_manifest_missing_version_audits_unresolvable(monkeypatch, tmp_path):
    catalog_dir = tmp_path / "catalog"
    nodes_dir = catalog_dir / "nodes"
    nodes_dir.mkdir(parents=True)
    (catalog_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (catalog_dir / "chains.json").write_text(
        json.dumps({"chains": [{"chain_id": "chain-1"}]}), encoding="utf-8"
    )

    references_module._catalog_index.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(references_module, "INDUSTRY_CATALOG_DIR", catalog_dir)
            result = audit_references(
                _version(
                    _reference(
                        namespace="industry_catalog_v1",
                        object_type="industry_catalog_chain",
                        object_id="chain-1",
                    )
                )
            )
    finally:
        references_module._catalog_index.cache_clear()

    assert result["issues"][0]["status"] == "unresolvable"


def test_hash_mismatch_reports_expected_and_actual_hash_details():
    resolved = resolve_theme_research_v1(_reference())
    assert resolved is not None
    actual_hash = content_sha256(resolved.payload)
    expected_hash = "0" * 64
    reference = _reference(
        version=resolved.version,
        content_hash=expected_hash,
    )

    result = audit_references(_version(reference))

    assert result["issues"] == [
        {
            "reference_id": "ref-1",
            "status": "hash_mismatch",
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "algorithm": "sha256-jcs-v1",
            "hash_scope": "entire_object",
        }
    ]


def test_missing_reference_does_not_modify_input_version():
    version = _version(
        _reference(
            object_type="v1_theme_node",
            object_id="missing-theme-node",
        )
    )
    original = deepcopy(version)

    result = audit_references(version)

    assert result["issues"] == [
        {"reference_id": "ref-1", "status": "missing"}
    ]
    assert version == original


def test_known_id_with_wrong_requested_type_is_type_mismatch():
    reference = _reference(
        object_type="v1_source",
        object_id="compute_accelerators_boards",
    )

    result = audit_references(_version(reference))

    assert result["issues"] == [
        {
            "reference_id": "ref-1",
            "status": "type_mismatch",
            "expected_type": "v1_source",
            "actual_type": "v1_theme_node",
        }
    ]


def test_reference_version_mismatch_reports_expected_and_actual():
    resolved = resolve_theme_research_v1(_reference())
    assert resolved is not None
    reference = _reference(version="obsolete-version")

    result = audit_references(_version(reference))

    assert result["issues"] == [
        {
            "reference_id": "ref-1",
            "status": "version_mismatch",
            "expected_version": "obsolete-version",
            "actual_version": resolved.version,
        }
    ]


def test_version_mismatch_precedes_invalid_selected_field_pointer(monkeypatch):
    def fake_resolver(reference):
        return ResolvedReference(
            namespace="theme_research_v1",
            object_type="v1_theme",
            object_id=reference["reference_object_id"],
            version="current-version",
            payload={},
        )

    monkeypatch.setitem(RESOLVERS, "theme_research_v1", fake_resolver)
    reference = _reference(
        version="old-version",
        hash_scope="selected_fields",
        hash_fields=["/missing"],
    )

    result = audit_references(_version(reference))

    assert result["issues"][0]["status"] == "version_mismatch"


def test_deprecated_resolver_result_is_reported(monkeypatch):
    payload = {"theme_id": "retired-theme"}

    def fake_resolver(reference):
        return ResolvedReference(
            namespace="theme_research_v1",
            object_type="v1_theme",
            object_id=reference["reference_object_id"],
            version="v1",
            payload=payload,
            deprecated=True,
        )

    monkeypatch.setitem(RESOLVERS, "theme_research_v1", fake_resolver)
    reference = _reference(
        object_id="retired-theme",
        version="v1",
        content_hash=content_sha256(payload),
    )

    result = audit_references(_version(reference))

    assert result["issues"] == [
        {"reference_id": "ref-1", "status": "deprecated"}
    ]


def test_deprecated_precedes_invalid_selected_field_pointer(monkeypatch):
    def fake_resolver(reference):
        return ResolvedReference(
            namespace="theme_research_v1",
            object_type="v1_theme",
            object_id=reference["reference_object_id"],
            version="v1",
            payload={},
            deprecated=True,
        )

    monkeypatch.setitem(RESOLVERS, "theme_research_v1", fake_resolver)
    reference = _reference(
        version="v1",
        hash_scope="selected_fields",
        hash_fields=["/missing"],
    )

    result = audit_references(_version(reference))

    assert result["issues"][0]["status"] == "deprecated"


def test_theme_child_inherits_archived_theme_artifact_status(monkeypatch, tmp_path):
    theme_dir = tmp_path / "theme_decomposition"
    mapping_dir = theme_dir / "company_mappings"
    mapping_dir.mkdir(parents=True)
    artifact = {
        "artifact_version": "theme-v1",
        "theme": {"theme_id": "archived-theme", "status": "archived"},
        "nodes": [{"node_id": "archived-node"}],
        "sources": [],
        "claims": [],
    }
    (theme_dir / "archived_theme.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    monkeypatch.setattr(references_module, "THEME_ARTIFACT_DIR", theme_dir)
    monkeypatch.setattr(references_module, "COMPANY_MAPPING_DIR", mapping_dir)
    references_module._theme_index.cache_clear()
    try:
        resolved = resolve_theme_research_v1(
            _reference(object_type="v1_theme_node", object_id="archived-node")
        )
    finally:
        references_module._theme_index.cache_clear()

    assert resolved is not None
    assert resolved.deprecated is True


def test_duplicate_key_marks_second_reference_without_resolving_it():
    resolved = resolve_theme_research_v1(_reference())
    assert resolved is not None
    first = _reference(
        reference_id="ref-1",
        version=resolved.version,
        content_hash=content_sha256(resolved.payload),
    )
    second = deepcopy(first)
    second["reference_id"] = "ref-2"

    result = audit_references(_version(first, second))

    assert result == {
        "status": "fail",
        "total": 2,
        "resolved": 1,
        "issues": [{"reference_id": "ref-2", "status": "duplicate"}],
    }


@pytest.mark.parametrize("namespace", ["external_document", "web_resource"])
def test_non_archived_namespace_is_unresolvable(namespace):
    reference = _reference(namespace=namespace)

    result = audit_references(_version(reference))

    assert result["issues"][0]["status"] == "unresolvable"


def test_source_content_hash_scope_is_unresolvable():
    reference = _reference(hash_scope="source_content")

    result = audit_references(_version(reference))

    assert result["issues"][0] == {
        "reference_id": "ref-1",
        "status": "unresolvable",
        "error_code": "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE",
    }


def test_source_content_is_unresolvable_before_missing_resolution():
    reference = _reference(
        object_type="v1_source",
        object_id="missing-source",
        hash_scope="source_content",
    )

    result = audit_references(_version(reference))

    assert result["issues"][0]["status"] == "unresolvable"


def test_json_pointer_supports_dict_list_and_rfc6901_escapes():
    payload = {"a/b": {"~key": ["zero", {"value": 2}]}}

    assert resolve_json_pointer(payload, "/a~1b/~0key/0") == "zero"
    assert resolve_json_pointer(payload, "/a~1b/~0key/1/value") == 2


@pytest.mark.parametrize(
    "path",
    [
        "",
        "not-a-pointer",
        "/bad~2escape",
        "/items/-",
        "/items/-1",
        "/items/+1",
        "/items/01",
        "/items/²",
        "/items/١",
        "/items/2",
    ],
)
def test_json_pointer_rejects_invalid_paths_without_leaking_builtin_errors(path):
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        resolve_json_pointer({"items": ["zero", "one"]}, path)

    assert exc_info.value.code == "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE"


def test_json_pointer_rejects_huge_ascii_index_without_leaking_value_error():
    path = "/items/" + "9" * 5000

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        resolve_json_pointer({"items": ["only"]}, path)

    assert exc_info.value.code == "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE"


def test_resolver_ambiguity_is_audit_unresolvable(monkeypatch):
    def ambiguous_resolver(reference):
        raise ResearchProjectV2Error(
            "Ambiguous V1 reference",
            code="RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE",
        )

    monkeypatch.setitem(RESOLVERS, "theme_research_v1", ambiguous_resolver)

    result = audit_references(_version(_reference()))

    assert result["issues"] == [
        {
            "reference_id": "ref-1",
            "status": "unresolvable",
            "error_code": "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE",
        }
    ]


def test_audit_does_not_modify_reference_or_resolved_payload(monkeypatch):
    payload = {"theme_id": "theme-1", "metadata": {"state": "stable"}}
    payload_before = deepcopy(payload)

    def fake_resolver(reference):
        return ResolvedReference(
            namespace="theme_research_v1",
            object_type="v1_theme",
            object_id="theme-1",
            version="v1",
            payload=payload,
        )

    monkeypatch.setitem(RESOLVERS, "theme_research_v1", fake_resolver)
    reference = _reference(
        object_id="theme-1",
        version="v1",
        content_hash=content_sha256(payload),
    )
    reference_before = deepcopy(reference)
    version = _version(reference)
    version_before = deepcopy(version)

    assert audit_references(version)["status"] == "pass"
    assert payload == payload_before
    assert reference == reference_before
    assert version == version_before
