import os
from dataclasses import dataclass, field
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _candidate_roots() -> list[Path]:
    repo_root = _repo_root()
    if repo_root.parent.name == ".worktrees":
        return [repo_root.parent.parent, repo_root]
    return [repo_root]


def _path_from_env(env_name: str, default_name: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if raw:
        return Path(raw)
    for root in _candidate_roots():
        candidate = root / default_name
        if candidate.exists():
            return candidate
    return _candidate_roots()[0] / default_name


@dataclass(frozen=True)
class Settings:
    research_service: str = "stock_research"
    hfq_service: str = "stock_hfq"
    qfq_service: str = "stock_qfq"
    default_market: str = "CN_A"
    default_currency: str = "CNY"
    selection_top_n: int = 20
    repo_root: Path = field(default_factory=_repo_root)
    output_root: Path = field(default_factory=lambda: _path_from_env("STOCK_RESEARCH_OUTPUT_ROOT", "outputs"))
    reports_root: Path = field(default_factory=lambda: _path_from_env("STOCK_RESEARCH_REPORTS_ROOT", "reports"))


SETTINGS = Settings()
