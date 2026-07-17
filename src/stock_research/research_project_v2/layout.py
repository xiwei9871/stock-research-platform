from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ResearchProjectLayout:
    root: Path

    @classmethod
    def default(cls) -> "ResearchProjectLayout":
        return cls(REPOSITORY_ROOT / "artifacts/research_projects/v2")

    @property
    def schema_dir(self) -> Path:
        return self.root / "schema"

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def index_path(self) -> Path:
        return self.root / "index/research_project_index_v2.json"

    def project_dir(self, project_slug: str) -> Path:
        return self.projects_dir / project_slug
