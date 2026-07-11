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
    root = _write_catalog_package(tmp_path)
    node_dir = root / "nodes"
    (node_dir / "semiconductor_equipment.json").unlink()
    _write_json(
        node_dir / "z_first_written.json",
        {"nodes": [{"node_id": "zeta_node"}]},
    )
    _write_json(
        node_dir / "a_second_written.json",
        {"nodes": [{"node_id": "alpha_node"}, {"node_id": "beta_node"}]},
    )
    composition_dir = root / "theme_compositions"
    _write_json(
        composition_dir / "z_first_written.json",
        {"theme_compositions": [{"composition_id": "zeta_composition"}]},
    )
    _write_json(
        composition_dir / "a_second_written.json",
        {
            "theme_compositions": [
                {"composition_id": "alpha_composition"},
                {"composition_id": "beta_composition"},
            ]
        },
    )

    catalog = load_industry_catalog(root)

    assert [row["node_id"] for row in catalog["nodes"]] == [
        "alpha_node",
        "beta_node",
        "zeta_node",
    ]
    assert [row["composition_id"] for row in catalog["theme_compositions"]] == [
        "alpha_composition",
        "beta_composition",
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


def _write_catalog_package(tmp_path: Path) -> Path:
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
    return root


def _load_error(root: Path) -> IndustryCatalogValidationError:
    with pytest.raises(IndustryCatalogValidationError) as exc_info:
        load_industry_catalog(root)
    return exc_info.value


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
