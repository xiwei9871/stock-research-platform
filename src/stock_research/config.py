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


def _theme_research_report_root_from_env() -> Path | None:
    raw = os.environ.get("THEME_RESEARCH_REPORT_ROOT", "").strip()
    if raw:
        return Path(raw)
    return None


@dataclass(frozen=True)
class Settings:
    research_service: str = "stock_research"
    theme_research_migration_service: str = field(
        default_factory=lambda: os.getenv(
            "THEME_RESEARCH_MIGRATION_SERVICE", "stock_research"
        ).strip()
        or "stock_research"
    )
    theme_research_runtime_service: str = field(
        default_factory=lambda: os.getenv(
            "THEME_RESEARCH_RUNTIME_SERVICE", "theme_research_runtime"
        ).strip()
        or "theme_research_runtime"
    )
    theme_research_report_index_service: str = field(
        default_factory=lambda: os.getenv(
            "THEME_RESEARCH_REPORT_INDEX_SERVICE",
            "theme_research_report_indexer",
        ).strip()
        or "theme_research_report_indexer"
    )
    theme_research_report_review_service: str = field(
        default_factory=lambda: os.getenv(
            "THEME_RESEARCH_REPORT_REVIEW_SERVICE",
            "theme_research_report_reviewer",
        ).strip()
        or "theme_research_report_reviewer"
    )
    hfq_service: str = "stock_hfq"
    qfq_service: str = "stock_qfq"
    default_market: str = "CN_A"
    default_currency: str = "CNY"
    selection_top_n: int = 20
    repo_root: Path = field(default_factory=_repo_root)
    output_root: Path = field(default_factory=lambda: _path_from_env("STOCK_RESEARCH_OUTPUT_ROOT", "outputs"))
    reports_root: Path = field(default_factory=lambda: _path_from_env("STOCK_RESEARCH_REPORTS_ROOT", "reports"))
    theme_research_report_root: Path | None = field(
        default_factory=_theme_research_report_root_from_env
    )
    theme_research_report_scan_interval_seconds: int = field(
        default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS", 60)
    )
    theme_research_report_max_manifest_bytes: int = field(
        default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES", 64 * 1024)
    )
    theme_research_report_max_markdown_bytes: int = field(
        default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES", 10 * 1024 * 1024)
    )
    theme_research_report_max_pdf_bytes: int = field(
        default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_MAX_PDF_BYTES", 50 * 1024 * 1024)
    )
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

    def __post_init__(self) -> None:
        if self.theme_research_report_root is None:
            object.__setattr__(
                self,
                "theme_research_report_root",
                self.reports_root / "theme-research",
            )
        else:
            object.__setattr__(
                self,
                "theme_research_report_root",
                Path(self.theme_research_report_root),
            )

        positive_settings = (
            (
                "THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS",
                "theme_research_report_scan_interval_seconds",
            ),
            (
                "THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES",
                "theme_research_report_max_manifest_bytes",
            ),
            (
                "THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES",
                "theme_research_report_max_markdown_bytes",
            ),
            (
                "THEME_RESEARCH_REPORT_MAX_PDF_BYTES",
                "theme_research_report_max_pdf_bytes",
            ),
        )
        for env_name, field_name in positive_settings:
            if getattr(self, field_name) <= 0:
                raise ValueError(
                    f"{env_name} ({field_name}) must be greater than zero"
                )


SETTINGS = Settings()
