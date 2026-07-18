from __future__ import annotations

import pytest


ALLOWED_EXACT_PATHS = {
    "src/stock_research/cli.py",
    "docs/superpowers/specs/2026-07-18-research-layer-separation-design.md",
    "docs/superpowers/plans/2026-07-18-industry-evidence-acquisition-r2a.md",
    "docs/research_operating_layer_v2_goal_and_roadmap.md",
}
ALLOWED_PREFIXES = (
    "artifacts/research_projects/v2_1/",
    "src/stock_research/research_project_v2_1/",
)


def is_r2a_path(path: str) -> bool:
    return (
        path in ALLOWED_EXACT_PATHS
        or path.startswith(ALLOWED_PREFIXES)
        or (
            path.startswith("tests/test_research_project_v2_1_")
            and path.endswith(".py")
        )
    )


@pytest.mark.parametrize(
    "path",
    [
        "artifacts/research_projects/v2_1/schema/source_record.schema.json",
        "src/stock_research/research_project_v2_1/layout.py",
        "tests/test_research_project_v2_1_layout.py",
        "src/stock_research/cli.py",
        "docs/superpowers/specs/2026-07-18-research-layer-separation-design.md",
        "docs/superpowers/plans/2026-07-18-industry-evidence-acquisition-r2a.md",
        "docs/research_operating_layer_v2_goal_and_roadmap.md",
    ],
)
def test_scope_guard_allows_only_planned_r2a_paths(path: str):
    assert is_r2a_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "artifacts/research_projects/v2/index/research_project_index_v2.json",
        "artifacts/theme_decomposition/theme.json",
        "artifacts/technology_industry_catalog/catalog.json",
        "dashboard/src/App.tsx",
        "src/stock_research/dashboard/api.py",
        "src/stock_research/research_project_v2/cli.py",
        "src/stock_research/theme_research_db_schema.py",
        "src/stock_research/migrations/001_add_research_table.sql",
        "src/stock_research/api/research_projects.py",
        "src/stock_research/company_rating.py",
        "src/stock_research/stock_rating.py",
        "tests/test_research_project_v2_storage.py",
        "docs/superpowers/plans/unrelated.md",
    ],
)
def test_scope_guard_rejects_r1_and_out_of_scope_paths(path: str):
    assert not is_r2a_path(path)
