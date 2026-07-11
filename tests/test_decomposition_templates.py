import json
from pathlib import Path

import pytest

from stock_research.decomposition_templates import (
    DECOMPOSITION_TEMPLATE_DIR,
    DecompositionTemplateValidationError,
    cli,
    initialize_theme_from_template,
    load_decomposition_template,
    load_decomposition_template_library,
    summarize_decomposition_template_library,
)
from stock_research.theme_decomposition import load_theme_package


def test_template_library_loads_three_reusable_families():
    library = load_decomposition_template_library()

    summary = summarize_decomposition_template_library(library)

    assert summary == {
        "example_theme_count": 2,
        "node_archetype_count": 21,
        "step_count": 24,
        "template_count": 3,
        "templates_by_family": {
            "head_to_toe": ["head_to_toe_v1"],
            "manufacturing_process": ["manufacturing_process_v1"],
            "system_bottleneck": ["system_bottleneck_v1"],
        },
    }


def test_existing_samples_are_registered_as_template_examples():
    system_template = load_decomposition_template("system_bottleneck_v1")
    body_template = load_decomposition_template("head_to_toe_v1")

    assert "ai_power_value_capture_v1" in system_template["example_theme_ids"]
    assert "humanoid_robotics_head_to_toe_v1" in body_template["example_theme_ids"]


@pytest.mark.parametrize(
    ("template_id", "theme_type"),
    [
        ("system_bottleneck_v1", "ai_compute"),
        ("head_to_toe_v1", "humanoid_robotics"),
        ("manufacturing_process_v1", "semiconductor_equipment"),
    ],
)
def test_initialized_theme_uses_existing_theme_schema(
    tmp_path: Path,
    template_id: str,
    theme_type: str,
):
    artifact = initialize_theme_from_template(
        template_id=template_id,
        theme_id=f"test_{theme_type}_v1",
        theme_name=f"Test {theme_type}",
        theme_type=theme_type,
        last_updated="2026-07-10",
    )
    artifact_dir = tmp_path / "themes"
    artifact_dir.mkdir()
    (artifact_dir / "theme.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package = load_theme_package(artifact_dir)

    assert package["themes"][0]["theme_id"] == f"test_{theme_type}_v1"
    assert artifact["artifact_version"] == "theme_decomposition_v1_5"
    assert artifact["theme"]["status"] == "draft"
    assert artifact["sources"] == []
    assert artifact["claims"] == []
    assert artifact["nodes"] == []
    assert artifact["decomposition_templates"][0]["theme_type"] == theme_type
    assert artifact["decomposition_templates"][0]["output_schema"] == "theme_decomposition_v1_5"


def test_initialization_rejects_incompatible_theme_type():
    with pytest.raises(DecompositionTemplateValidationError) as exc_info:
        initialize_theme_from_template(
            template_id="head_to_toe_v1",
            theme_id="invalid_ai_power",
            theme_name="Invalid",
            theme_type="ai_power",
            last_updated="2026-07-10",
        )

    assert exc_info.value.code == "INCOMPATIBLE_THEME_TYPE"


def test_duplicate_step_order_is_rejected(tmp_path: Path):
    artifact_dir = _copy_template_library(tmp_path)
    path = artifact_dir / "system_bottleneck_template.json"
    payload = _read_json(path)
    payload["template"]["steps"][1]["order"] = payload["template"]["steps"][0]["order"]
    _write_json(path, payload)

    error = _load_invalid_library(artifact_dir)

    assert error.code == "DUPLICATE_STEP_ORDER"


def test_step_without_quality_gate_is_rejected(tmp_path: Path):
    artifact_dir = _copy_template_library(tmp_path)
    path = artifact_dir / "head_to_toe_template.json"
    payload = _read_json(path)
    payload["template"]["steps"][0]["quality_gates"] = []
    _write_json(path, payload)

    error = _load_invalid_library(artifact_dir)

    assert error.code == "STEP_REQUIRES_QUALITY_GATE"


def test_invalid_claim_type_is_rejected(tmp_path: Path):
    artifact_dir = _copy_template_library(tmp_path)
    path = artifact_dir / "manufacturing_process_template.json"
    payload = _read_json(path)
    payload["template"]["claim_types"].append("buy_signal")
    _write_json(path, payload)

    error = _load_invalid_library(artifact_dir)

    assert error.code == "INVALID_CLAIM_TYPE"


def test_invalid_node_type_is_rejected(tmp_path: Path):
    artifact_dir = _copy_template_library(tmp_path)
    path = artifact_dir / "manufacturing_process_template.json"
    payload = _read_json(path)
    payload["template"]["node_archetypes"][0]["allowed_node_types"] = ["factory_magic"]
    _write_json(path, payload)

    error = _load_invalid_library(artifact_dir)

    assert error.code == "INVALID_NODE_TYPE"


def test_orphan_node_archetype_is_rejected(tmp_path: Path):
    artifact_dir = _copy_template_library(tmp_path)
    path = artifact_dir / "system_bottleneck_template.json"
    payload = _read_json(path)
    payload["template"]["node_archetypes"][1]["parent_archetype_id"] = "missing_parent"
    _write_json(path, payload)

    error = _load_invalid_library(artifact_dir)

    assert error.code == "ORPHAN_NODE_ARCHETYPE"


def test_cli_validate_and_initialize_emit_json(capsys):
    validate_exit = cli(["validate"])
    validate_payload = json.loads(capsys.readouterr().out)

    initialize_exit = cli(
        [
            "initialize",
            "--template",
            "system_bottleneck_v1",
            "--theme-id",
            "ai_compute_supply_v1",
            "--theme-name",
            "AI Compute Supply",
            "--theme-type",
            "ai_compute",
            "--last-updated",
            "2026-07-10",
        ]
    )
    initialized = json.loads(capsys.readouterr().out)

    assert validate_exit == 0
    assert validate_payload["status"] == "ok"
    assert validate_payload["template_count"] == 3
    assert initialize_exit == 0
    assert initialized["theme"]["theme_id"] == "ai_compute_supply_v1"
    assert initialized["decomposition_templates"][0]["template_id"] == "system_bottleneck_v1"


def _copy_template_library(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "decomposition_templates"
    artifact_dir.mkdir()
    for path in DECOMPOSITION_TEMPLATE_DIR.glob("*.json"):
        _write_json(artifact_dir / path.name, _read_json(path))
    return artifact_dir


def _load_invalid_library(artifact_dir: Path) -> DecompositionTemplateValidationError:
    with pytest.raises(DecompositionTemplateValidationError) as exc_info:
        load_decomposition_template_library(artifact_dir)
    return exc_info.value


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
