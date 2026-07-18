from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class LayeredResearchLayout:
    root: Path

    @classmethod
    def default(cls) -> "LayeredResearchLayout":
        return cls(REPOSITORY_ROOT / "artifacts/research_projects/v2_1")

    @property
    def schema_dir(self) -> Path:
        return self.root / "schema"

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def evidence_discovery_dir(self) -> Path:
        return self.root / "evidence/discovery"

    @property
    def evidence_raw_dir(self) -> Path:
        return self.root / "evidence/raw"

    @property
    def evidence_metadata_dir(self) -> Path:
        return self.root / "evidence/metadata"

    @property
    def evidence_normalized_dir(self) -> Path:
        return self.root / "evidence/normalized"

    @property
    def evidence_assessments_dir(self) -> Path:
        return self.root / "evidence/assessments"

    @property
    def index_path(self) -> Path:
        return self.root / "index/research_project_index_v2_1.json"

    def project_dir(self, project_slug: str) -> Path:
        return self.projects_dir / project_slug
