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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


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
    dashboard_auth_required: bool = field(
        default_factory=lambda: _env_bool("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", False)
    )
    dashboard_cookie_secure: bool = field(
        default_factory=lambda: _env_bool("STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE", False)
    )
    dashboard_session_cookie: str = "stock_research_session"
    dashboard_csrf_cookie: str = "stock_research_csrf"
    dashboard_session_ttl_seconds: int = field(
        default_factory=lambda: _env_int("STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS", 60 * 60 * 12)
    )


SETTINGS = Settings()
