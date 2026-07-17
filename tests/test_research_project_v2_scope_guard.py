from __future__ import annotations

from pathlib import Path, PurePosixPath
import re


SCOPE_EVIDENCE = Path("/private/tmp/research_project_v2_changed_files.txt")

EXACT_ALLOWED = {
    "pyproject.toml",
    "src/stock_research/cli.py",
    "docs/research_operating_layer_v2_current_state_audit.md",
    "docs/research_operating_layer_v2_goal_and_roadmap.md",
    "docs/research_operating_layer_v2_r1.md",
    "docs/superpowers/plans/2026-07-13-research-operating-layer-v2-implementation-plan.md",
    "docs/superpowers/specs/2026-07-13-research-operating-layer-v2-design.md",
}

ALLOWED_PATTERNS = (
    re.compile(r"^src/stock_research/research_project_v2/[^/]+\.py$"),
    re.compile(r"^artifacts/research_projects/v2/.+$"),
    re.compile(r"^tests/test_research_project_v2_[^/]+\.py$"),
)

FORBIDDEN_PATTERNS = (
    re.compile(r"^artifacts/theme_decomposition(?:/|$)"),
    re.compile(r"^artifacts/technology_industry_catalog(?:/|$)"),
    re.compile(r"^dashboard(?:/|$)"),
    re.compile(r"^src/stock_research/dashboard(?:/|$)"),
    re.compile(r"^src/stock_research/theme_research_db_schema\.py$"),
    re.compile(r"(^|/)(?:migrations?|alembic)(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:db|database)[_-]?schema(?:[./_-]|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:api[_-]?routes?|routes?[_-]?api)(?:[./_-]|$)", re.IGNORECASE),
)

PRODUCTION_MIGRATION_FILENAME = re.compile(
    r"(^|/)(?:V?\d{3,}[^/]*\.(?:sql|py)|[^/]*migration[^/]*\.(?:sql|py))$",
    re.IGNORECASE,
)


def _changed_files() -> list[str]:
    assert SCOPE_EVIDENCE.is_file(), (
        f"scope evidence is required at {SCOPE_EVIDENCE}; generate it by taking the "
        "sorted unique union of `git show --pretty='' --name-only <each-R1-commit>` "
        "and the three Task10 paths (never use a broad commit range)"
    )
    paths = [line.strip() for line in SCOPE_EVIDENCE.read_text().splitlines() if line.strip()]
    assert paths, f"scope evidence is empty: {SCOPE_EVIDENCE}"
    assert paths == sorted(set(paths)), "scope evidence must be sorted and deduplicated"
    return paths


def _is_allowed(path: str) -> bool:
    return path in EXACT_ALLOWED or any(pattern.fullmatch(path) for pattern in ALLOWED_PATTERNS)


def test_r1_changed_files_stay_inside_the_research_project_v2_scope() -> None:
    changed = _changed_files()
    forbidden = [
        path for path in changed if any(pattern.search(path) for pattern in FORBIDDEN_PATTERNS)
    ]
    outside_allowlist = [path for path in changed if not _is_allowed(path)]

    assert forbidden == [], f"R1 scope contains forbidden paths: {forbidden}"
    assert outside_allowlist == [], f"R1 scope contains paths outside the allowlist: {outside_allowlist}"


def test_r1_does_not_add_production_migration_files() -> None:
    changed = _changed_files()
    migration_files = [
        path
        for path in changed
        if PRODUCTION_MIGRATION_FILENAME.search(PurePosixPath(path).as_posix())
    ]
    assert migration_files == [], f"R1 contains production migration filenames: {migration_files}"
