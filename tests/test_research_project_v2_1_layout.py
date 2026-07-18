from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from stock_research.research_project_v2.layout import ResearchProjectLayout
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


def test_default_layout_points_at_isolated_v2_1_artifact_root():
    layout = LayeredResearchLayout.default()

    assert layout.root.name == "v2_1"
    assert layout.root != ResearchProjectLayout.default().root
    assert layout.schema_dir == layout.root / "schema"
    assert layout.projects_dir == layout.root / "projects"
    assert layout.evidence_discovery_dir == layout.root / "evidence/discovery"
    assert layout.evidence_raw_dir == layout.root / "evidence/raw"
    assert layout.evidence_metadata_dir == layout.root / "evidence/metadata"
    assert layout.evidence_normalized_dir == layout.root / "evidence/normalized"
    assert layout.evidence_assessments_dir == layout.root / "evidence/assessments"
    assert layout.index_path == layout.root / "index/research_project_index_v2_1.json"
    assert layout.project_dir("demo") == layout.projects_dir / "demo"


def test_layout_is_frozen():
    layout = LayeredResearchLayout(Path("unused"))

    with pytest.raises(FrozenInstanceError):
        layout.root = Path("replacement")


def test_constructing_and_accessing_layout_has_no_filesystem_side_effects(tmp_path: Path):
    root = tmp_path / "not-created"
    layout = LayeredResearchLayout(root)

    _ = (
        layout.schema_dir,
        layout.projects_dir,
        layout.evidence_discovery_dir,
        layout.evidence_raw_dir,
        layout.evidence_metadata_dir,
        layout.evidence_normalized_dir,
        layout.evidence_assessments_dir,
        layout.index_path,
        layout.project_dir("demo"),
    )

    assert not root.exists()
    assert list(tmp_path.iterdir()) == []
