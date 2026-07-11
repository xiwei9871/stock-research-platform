import json
from pathlib import Path

import pytest

from stock_research.technology_industry_catalog import (
    IndustryCatalogValidationError,
    load_industry_catalog,
)


def test_load_industry_catalog_composes_package_files(tmp_path: Path):
    root = _write_catalog_package(tmp_path)

    catalog = load_industry_catalog(root)

    assert catalog["artifact_version"] == "technology_industry_catalog_v1"
    assert [row["sector_id"] for row in catalog["sectors"]] == ["semiconductor_electronics"]
    assert [row["chain_id"] for row in catalog["chains"]] == ["semiconductor_equipment"]
    assert [row["node_id"] for row in catalog["nodes"]] == ["lithography", "duv_lithography"]
    assert catalog["edges"] == []
    assert catalog["theme_compositions"] == []
    assert [row["source_id"] for row in catalog["sources"]] == ["asml_chip_manufacturing"]


def test_load_industry_catalog_flattens_sorted_package_files(tmp_path: Path):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    node_dir = root / "nodes"
    _write_json(
        node_dir / "z_first_written.json",
        {"nodes": [_canonical_l3_node("zeta_node")]},
    )
    _write_json(
        node_dir / "a_second_written.json",
        {
            "nodes": [
                _canonical_l3_node("alpha_node"),
                _canonical_l3_node("beta_node"),
            ]
        },
    )
    composition_dir = root / "theme_compositions"
    _write_json(
        composition_dir / "z_first_written.json",
        {"theme_compositions": [_theme_composition("zeta_composition")]},
    )
    _write_json(
        composition_dir / "a_second_written.json",
        {
            "theme_compositions": [
                _theme_composition("alpha_composition"),
                _theme_composition("beta_composition"),
            ]
        },
    )

    catalog = load_industry_catalog(root)

    assert [row["node_id"] for row in catalog["nodes"]] == [
        "alpha_node",
        "beta_node",
        "application_stage",
        "application_role",
        "lithography",
        "duv_lithography",
        "zeta_node",
    ]
    assert [row["composition_id"] for row in catalog["theme_compositions"]] == [
        "alpha_composition",
        "beta_composition",
        "application_role_composition",
        "zeta_composition",
    ]


def test_missing_artifact_directory_has_stable_error(tmp_path: Path):
    error = _load_error(tmp_path / "missing")

    assert error.code == "ARTIFACT_DIR_NOT_FOUND"


def test_missing_manifest_has_stable_error(tmp_path: Path):
    root = tmp_path / "technology_industry_catalog"
    root.mkdir()

    error = _load_error(root)

    assert error.code == "MANIFEST_NOT_FOUND"


def test_missing_named_file_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    (root / "sectors.json").unlink()

    error = _load_error(root)

    assert error.code == "PACKAGE_FILE_NOT_FOUND"


def test_invalid_json_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    (root / "chains.json").write_text("{invalid", encoding="utf-8")

    error = _load_error(root)

    assert error.code == "INVALID_JSON"


def test_invalid_utf8_has_stable_json_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    (root / "chains.json").write_bytes(b"\xff")

    error = _load_error(root)

    assert error.code == "INVALID_JSON"


def test_json_root_must_be_object(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    _write_json(root / "sources.json", [])

    error = _load_error(root)

    assert error.code == "INVALID_JSON_ROOT"


def test_missing_artifact_version_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    manifest = _read_json(root / "manifest.json")
    del manifest["artifact_version"]
    _write_json(root / "manifest.json", manifest)

    error = _load_error(root)

    assert error.code == "MISSING_ARTIFACT_VERSION"


def test_unsupported_artifact_version_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    manifest = _read_json(root / "manifest.json")
    manifest["artifact_version"] = "technology_industry_catalog_v0"
    _write_json(root / "manifest.json", manifest)

    error = _load_error(root)

    assert error.code == "UNSUPPORTED_ARTIFACT_VERSION"


@pytest.mark.parametrize(
    "manifest_key",
    [
        "sector_file",
        "chain_file",
        "edge_file",
        "source_file",
        "node_dir",
        "theme_composition_dir",
    ],
)
def test_missing_required_manifest_key_has_stable_error(tmp_path: Path, manifest_key: str):
    root = _write_catalog_package(tmp_path)
    manifest = _read_json(root / "manifest.json")
    del manifest[manifest_key]
    _write_json(root / "manifest.json", manifest)

    error = _load_error(root)

    assert error.code == "MISSING_MANIFEST_KEY"


def test_manifest_package_path_must_be_string(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    manifest = _read_json(root / "manifest.json")
    manifest["sector_file"] = None
    _write_json(root / "manifest.json", manifest)

    error = _load_error(root)

    assert error.code == "INVALID_MANIFEST_PATH"


@pytest.mark.parametrize("directory_name", ["nodes", "theme_compositions"])
def test_missing_named_directory_has_stable_error(tmp_path: Path, directory_name: str):
    root = _write_catalog_package(tmp_path)
    directory = root / directory_name
    for path in directory.iterdir():
        path.unlink()
    directory.rmdir()

    error = _load_error(root)

    assert error.code == "PACKAGE_DIRECTORY_NOT_FOUND"


@pytest.mark.parametrize(
    ("relative_path", "collection_key"),
    [
        ("sectors.json", "sectors"),
        ("chains.json", "chains"),
        ("edges.json", "edges"),
        ("sources.json", "sources"),
        ("nodes/semiconductor_equipment.json", "nodes"),
        ("theme_compositions/compositions.json", "theme_compositions"),
    ],
)
def test_package_collection_must_be_list(
    tmp_path: Path,
    relative_path: str,
    collection_key: str,
):
    root = _write_catalog_package(tmp_path)
    _write_json(root / relative_path, {collection_key: {}})

    error = _load_error(root)

    assert error.code == "INVALID_COLLECTION"


def test_missing_package_collection_key_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    _write_json(root / "edges.json", {})

    error = _load_error(root)

    assert error.code == "MISSING_COLLECTION_KEY"


@pytest.mark.parametrize(
    ("relative_path", "collection_key", "field"),
    [
        ("sectors.json", "sectors", "description"),
        ("chains.json", "chains", "scope"),
        ("nodes/semiconductor_equipment.json", "nodes", "node_type"),
        ("edges.json", "edges", "notes"),
        ("theme_compositions/compositions.json", "theme_compositions", "notes"),
        ("sources.json", "sources", "publisher"),
    ],
)
def test_rows_require_all_fields_deterministically(
    tmp_path: Path,
    relative_path: str,
    collection_key: str,
    field: str,
):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    payload = _read_json(root / relative_path)
    del payload[collection_key][0][field]
    _write_json(root / relative_path, payload)

    error = _load_error(root)

    assert error.code == "MISSING_REQUIRED_FIELD"
    assert field in str(error)


@pytest.mark.parametrize(
    ("relative_path", "collection_key", "field"),
    [
        ("sectors.json", "sectors", "sector_id"),
        ("sectors.json", "sectors", "sector_name"),
        ("chains.json", "chains", "chain_id"),
        ("chains.json", "chains", "chain_name"),
        ("nodes/semiconductor_equipment.json", "nodes", "node_id"),
        ("nodes/semiconductor_equipment.json", "nodes", "node_name"),
        ("edges.json", "edges", "edge_id"),
        ("theme_compositions/compositions.json", "theme_compositions", "composition_id"),
        ("sources.json", "sources", "source_id"),
    ],
)
def test_ids_and_names_must_be_non_empty(
    tmp_path: Path,
    relative_path: str,
    collection_key: str,
    field: str,
):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    payload = _read_json(root / relative_path)
    payload[collection_key][0][field] = "   "
    _write_json(root / relative_path, payload)

    error = _load_error(root)

    assert error.code == "MISSING_REQUIRED_FIELD"
    assert field in str(error)


def test_duplicate_sector_id_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    payload = _read_json(root / "sectors.json")
    payload["sectors"].append(dict(payload["sectors"][0]))
    _write_json(root / "sectors.json", payload)

    assert _load_error(root).code == "DUPLICATE_SECTOR_ID"


def test_orphan_chain_sector_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    _mutate_first(root / "chains.json", "chains", sector_id="missing_sector")

    assert _load_error(root).code == "ORPHAN_CHAIN_SECTOR"


def test_invalid_chain_kind_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    _mutate_first(root / "chains.json", "chains", chain_kind="invalid")

    assert _load_error(root).code == "INVALID_CHAIN_KIND"


def test_invalid_decomposition_method_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    _mutate_first(root / "chains.json", "chains", decomposition_method="invalid")

    assert _load_error(root).code == "INVALID_DECOMPOSITION_METHOD"


def test_duplicate_node_id_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    payload["nodes"].append(dict(payload["nodes"][0]))
    _write_json(path, payload)

    assert _load_error(root).code == "DUPLICATE_NODE_ID"


def test_orphan_node_chain_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    payload["nodes"][0]["chain_id"] = "missing_chain"
    _write_json(path, payload)

    assert _load_error(root).code == "ORPHAN_NODE_CHAIN"


def test_invalid_node_level_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    payload["nodes"][0]["level"] = "L2"
    _write_json(path, payload)

    assert _load_error(root).code == "INVALID_NODE_LEVEL"


@pytest.mark.parametrize(
    ("chain_kind", "node_kind"),
    [
        ("canonical_industry_chain", "application_role"),
        ("canonical_industry_chain", "frontier_route"),
        ("application_theme_chain", "canonical"),
        ("frontier_technology_chain", "application_role"),
    ],
)
def test_node_kind_must_match_chain_kind(
    tmp_path: Path,
    chain_kind: str,
    node_kind: str,
):
    root = _write_catalog_package(tmp_path)
    _mutate_first(root / "chains.json", "chains", chain_kind=chain_kind)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    payload["nodes"][0]["node_kind"] = node_kind
    payload["nodes"][1]["node_kind"] = node_kind
    _write_json(path, payload)

    assert _load_error(root).code == "INVALID_NODE_KIND_FOR_CHAIN"


def test_l3_parent_node_id_must_be_null(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    payload["nodes"][0]["parent_node_id"] = "duv_lithography"
    _write_json(path, payload)

    assert _load_error(root).code == "ORPHAN_NODE_PARENT"


@pytest.mark.parametrize("parent_mutation", ["missing", "l4", "other_chain"])
def test_l4_parent_must_be_l3_in_same_chain(tmp_path: Path, parent_mutation: str):
    root = _write_catalog_package(tmp_path)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    if parent_mutation == "missing":
        payload["nodes"][1]["parent_node_id"] = "missing_parent"
    elif parent_mutation == "l4":
        payload["nodes"][1]["parent_node_id"] = "duv_lithography"
    else:
        _add_chain(root, "other_chain", "canonical_industry_chain")
        payload["nodes"].append(_canonical_l3_node("other_parent", chain_id="other_chain"))
        payload["nodes"][1]["parent_node_id"] = "other_parent"
    _write_json(path, payload)

    assert _load_error(root).code == "ORPHAN_NODE_PARENT"


def test_application_roles_cannot_own_canonical_key(tmp_path: Path):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    path = root / "nodes" / "application_theme.json"
    payload = _read_json(path)
    payload["nodes"][1]["canonical_key"] = "owned.by.application"
    _write_json(path, payload)

    assert _load_error(root).code == "INVALID_NODE_KIND_FOR_CHAIN"


def test_duplicate_canonical_ownership_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    duplicate = dict(payload["nodes"][1])
    duplicate["node_id"] = "second_duv_lithography"
    duplicate["primary_path"] = [
        "semiconductor_electronics",
        "semiconductor_equipment",
        "lithography",
        "second_duv_lithography",
    ]
    payload["nodes"].append(duplicate)
    _write_json(path, payload)

    assert _load_error(root).code == "DUPLICATE_CANONICAL_OWNERSHIP"


def test_canonical_l4_primary_path_has_stable_error(tmp_path: Path):
    root = _write_catalog_package(tmp_path)
    path = root / "nodes" / "semiconductor_equipment.json"
    payload = _read_json(path)
    payload["nodes"][1]["primary_path"] = ["wrong"]
    _write_json(path, payload)

    assert _load_error(root).code == "INVALID_PRIMARY_PATH"


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("source_node_id", "ORPHAN_EDGE_SOURCE"),
        ("target_node_id", "ORPHAN_EDGE_TARGET"),
    ],
)
def test_edge_endpoints_have_stable_errors(tmp_path: Path, field: str, code: str):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    _mutate_first(root / "edges.json", "edges", **{field: "missing_node"})

    assert _load_error(root).code == code


@pytest.mark.parametrize("reference", ["missing_node", "lithography", "application_role"])
def test_node_canonical_refs_must_resolve_to_canonical_l4_nodes(
    tmp_path: Path,
    reference: str,
):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    path = root / "nodes" / "application_theme.json"
    payload = _read_json(path)
    payload["nodes"][1]["canonical_node_refs"] = [reference]
    _write_json(path, payload)

    assert _load_error(root).code == "INVALID_CANONICAL_NODE_REFERENCE"


def test_composition_canonical_refs_must_resolve_to_canonical_l4_nodes(tmp_path: Path):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    _mutate_first(
        root / "theme_compositions" / "compositions.json",
        "theme_compositions",
        canonical_node_refs=["missing_node"],
    )

    assert _load_error(root).code == "INVALID_CANONICAL_NODE_REFERENCE"


@pytest.mark.parametrize(
    ("role_node_id", "code"),
    [
        ("missing_role", "ORPHAN_COMPOSITION_ROLE"),
        ("duv_lithography", "INVALID_COMPOSITION_ROLE"),
    ],
)
def test_composition_role_must_resolve_to_application_role(
    tmp_path: Path,
    role_node_id: str,
    code: str,
):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    _mutate_first(
        root / "theme_compositions" / "compositions.json",
        "theme_compositions",
        role_node_id=role_node_id,
    )

    assert _load_error(root).code == code


def test_composition_chain_must_resolve(tmp_path: Path):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    _mutate_first(
        root / "theme_compositions" / "compositions.json",
        "theme_compositions",
        chain_id="missing_chain",
    )

    assert _load_error(root).code == "ORPHAN_COMPOSITION_CHAIN"


def test_validation_raises_first_error_in_artifact_order(tmp_path: Path):
    root = _write_catalog_package(tmp_path, include_relationships=True)
    _mutate_first(root / "sectors.json", "sectors", sector_id="")
    _mutate_first(root / "chains.json", "chains", chain_kind="invalid")
    _mutate_first(root / "edges.json", "edges", source_node_id="missing")

    assert _load_error(root).code == "MISSING_REQUIRED_FIELD"


def _write_catalog_package(
    tmp_path: Path,
    *,
    include_relationships: bool = False,
) -> Path:
    root = tmp_path / "technology_industry_catalog"
    node_dir = root / "nodes"
    theme_composition_dir = root / "theme_compositions"
    node_dir.mkdir(parents=True)
    theme_composition_dir.mkdir()

    _write_json(
        root / "manifest.json",
        {
            "artifact_version": "technology_industry_catalog_v1",
            "catalog_id": "test_catalog",
            "status": "draft",
            "sector_file": "sectors.json",
            "chain_file": "chains.json",
            "edge_file": "edges.json",
            "source_file": "sources.json",
            "node_dir": "nodes",
            "theme_composition_dir": "theme_compositions",
        },
    )
    _write_json(
        root / "sectors.json",
        {
            "sectors": [
                {
                    "sector_id": "semiconductor_electronics",
                    "sector_name": "Semiconductor and electronic core industries",
                    "description": "Semiconductor and electronic component industries.",
                    "status": "draft",
                    "order": 1,
                }
            ]
        },
    )
    _write_json(
        root / "chains.json",
        {
            "chains": [
                {
                    "chain_id": "semiconductor_equipment",
                    "sector_id": "semiconductor_electronics",
                    "chain_name": "Semiconductor manufacturing equipment",
                    "chain_kind": "canonical_industry_chain",
                    "decomposition_method": "manufacturing_process",
                    "description": "Equipment used across semiconductor manufacturing.",
                    "scope": "Wafer-fabrication process equipment.",
                    "exclusions": [],
                    "aliases": [],
                    "status": "draft",
                    "order": 1,
                }
            ]
        },
    )
    _write_json(root / "edges.json", {"edges": []})
    _write_json(
        root / "sources.json",
        {
            "sources": [
                {
                    "source_id": "asml_chip_manufacturing",
                    "title": "How microchips are made",
                    "publisher": "ASML",
                    "url": "https://www.asml.com/en/technology/all-about-microchips/how-microchips-are-made",
                    "source_type": "industry_process_reference",
                    "notes": "Test fixture source.",
                }
            ]
        },
    )
    _write_json(
        node_dir / "semiconductor_equipment.json",
        {
            "nodes": [
                {
                    "node_id": "lithography",
                    "chain_id": "semiconductor_equipment",
                    "parent_node_id": None,
                    "level": "L3",
                    "node_name": "Lithography and patterning",
                    "node_kind": "canonical",
                    "node_type": "manufacturing_stage",
                    "description": "Pattern-transfer process family.",
                    "status": "draft",
                    "primary_path": [
                        "semiconductor_electronics",
                        "semiconductor_equipment",
                        "lithography",
                    ],
                    "canonical_key": "",
                    "canonical_node_refs": [],
                },
                {
                    "node_id": "duv_lithography",
                    "chain_id": "semiconductor_equipment",
                    "parent_node_id": "lithography",
                    "level": "L4",
                    "node_name": "DUV lithography equipment",
                    "node_kind": "canonical",
                    "node_type": "equipment",
                    "description": "Deep-ultraviolet lithography equipment.",
                    "status": "draft",
                    "primary_path": [
                        "semiconductor_electronics",
                        "semiconductor_equipment",
                        "lithography",
                        "duv_lithography",
                    ],
                    "canonical_key": "semiconductor_equipment.duv_lithography",
                    "canonical_node_refs": [],
                },
            ]
        },
    )
    if include_relationships:
        _add_chain(root, "application_theme", "application_theme_chain")
        _write_json(
            node_dir / "application_theme.json",
            {
                "nodes": [
                    {
                        "node_id": "application_stage",
                        "chain_id": "application_theme",
                        "parent_node_id": None,
                        "level": "L3",
                        "node_name": "Application stage",
                        "node_kind": "application_role",
                        "node_type": "application_stage",
                        "description": "Application-stage grouping.",
                        "status": "draft",
                        "primary_path": [
                            "semiconductor_electronics",
                            "application_theme",
                            "application_stage",
                        ],
                        "canonical_key": "",
                        "canonical_node_refs": [],
                    },
                    {
                        "node_id": "application_role",
                        "chain_id": "application_theme",
                        "parent_node_id": "application_stage",
                        "level": "L4",
                        "node_name": "Application role",
                        "node_kind": "application_role",
                        "node_type": "application_role",
                        "description": "Application role referencing canonical equipment.",
                        "status": "draft",
                        "primary_path": [
                            "semiconductor_electronics",
                            "application_theme",
                            "application_stage",
                            "application_role",
                        ],
                        "canonical_key": "",
                        "canonical_node_refs": ["duv_lithography"],
                    },
                ]
            },
        )
        _write_json(
            root / "edges.json",
            {
                "edges": [
                    {
                        "edge_id": "application_uses_duv",
                        "source_node_id": "application_role",
                        "target_node_id": "duv_lithography",
                        "relationship_type": "uses",
                        "notes": "Valid fixture edge.",
                        "source_ids": ["asml_chip_manufacturing"],
                    }
                ]
            },
        )
        _write_json(
            theme_composition_dir / "compositions.json",
            {
                "theme_compositions": [
                    {
                        "composition_id": "application_role_composition",
                        "chain_id": "application_theme",
                        "role_node_id": "application_role",
                        "canonical_node_refs": ["duv_lithography"],
                        "relationship_type": "uses",
                        "notes": "Valid fixture composition.",
                    }
                ]
            },
        )
    return root


def _canonical_l3_node(node_id: str, *, chain_id: str = "semiconductor_equipment") -> dict:
    return {
        "node_id": node_id,
        "chain_id": chain_id,
        "parent_node_id": None,
        "level": "L3",
        "node_name": node_id.replace("_", " ").title(),
        "node_kind": "canonical",
        "node_type": "manufacturing_stage",
        "description": "Canonical L3 test node.",
        "status": "draft",
        "primary_path": ["semiconductor_electronics", chain_id, node_id],
        "canonical_key": "",
        "canonical_node_refs": [],
    }


def _theme_composition(composition_id: str) -> dict:
    return {
        "composition_id": composition_id,
        "chain_id": "application_theme",
        "role_node_id": "application_role",
        "canonical_node_refs": ["duv_lithography"],
        "relationship_type": "uses",
        "notes": "Valid sorted composition fixture.",
    }


def _add_chain(root: Path, chain_id: str, chain_kind: str) -> None:
    path = root / "chains.json"
    payload = _read_json(path)
    payload["chains"].append(
        {
            "chain_id": chain_id,
            "sector_id": "semiconductor_electronics",
            "chain_name": chain_id.replace("_", " ").title(),
            "chain_kind": chain_kind,
            "decomposition_method": "infrastructure_flow",
            "description": "Additional test chain.",
            "scope": "Test scope.",
            "exclusions": [],
            "aliases": [],
            "status": "draft",
            "order": len(payload["chains"]) + 1,
        }
    )
    _write_json(path, payload)


def _mutate_first(path: Path, collection_key: str, **changes: object) -> None:
    payload = _read_json(path)
    payload[collection_key][0].update(changes)
    _write_json(path, payload)


def _load_error(root: Path) -> IndustryCatalogValidationError:
    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        load_industry_catalog(root)
    return exc_info.value


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
