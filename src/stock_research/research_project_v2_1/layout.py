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
    def evidence_metadata_v2_3_dir(self) -> Path:
        return self.root / "evidence/metadata_v2_3"

    @property
    def evidence_normalized_dir(self) -> Path:
        return self.root / "evidence/normalized"

    @property
    def evidence_assessments_dir(self) -> Path:
        return self.root / "evidence/assessments"

    @property
    def acquisition_attempts_dir(self) -> Path:
        return self.root / "acquisition/attempts"

    @property
    def acquisition_checkpoints_dir(self) -> Path:
        return self.root / "acquisition/checkpoints"

    @property
    def acquisition_import_requests_dir(self) -> Path:
        return self.root / "acquisition/import_requests"

    @property
    def acquisition_diagnostics_dir(self) -> Path:
        return self.root / "acquisition/diagnostics"

    @property
    def index_path(self) -> Path:
        return self.root / "index/research_project_index_v2_1.json"

    def project_dir(self, project_slug: str) -> Path:
        return self.projects_dir / project_slug
