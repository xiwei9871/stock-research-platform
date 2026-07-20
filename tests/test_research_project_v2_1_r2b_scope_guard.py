from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
R2B_PHASE1_SEED = "dec9187"
APPROVED_R2B_COMMITS: tuple[str, ...] = ()

ALLOWED_EXACT_PATHS = {
    "docs/research_operating_layer_v2_r2b_plan.md",
    "docs/research_operating_layer_v2_r2b_schema_extension_proposal.md",
    "src/stock_research/cli.py",
}
ALLOWED_PREFIXES = (
    "artifacts/research_projects/v2_1/schema/",
    "artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck/",
    "artifacts/research_projects/v2_1/evidence/",
    "artifacts/research_projects/v2_1/index/",
    "src/stock_research/research_project_v2_1/",
    "tests/test_research_project_v2_1_r2b_",
    "tests/test_research_project_v2_1_diff.py",
    "tests/test_research_project_v2_1_bottleneck_gate.py",
    "docs/research_operating_layer_v2_r2b_ai_compute_pcb_",
)
FORBIDDEN_PREFIXES = (
    "artifacts/research_projects/v2/",
    "artifacts/theme_decomposition/",
    "artifacts/technology_industry_catalog/",
    "dashboard/",
    "src/stock_research/dashboard/",
    "artifacts/research_projects/v2_1/projects/high_end_medical_device_industry_bottleneck/",
    "artifacts/research_projects/v2_1/projects/humanoid_robot_industry_bottleneck/",
    "artifacts/research_projects/v2_1/projects/new_energy_storage_industry_bottleneck/",
)
FORBIDDEN_COMPONENTS = {"api", "database", "db", "migration", "migrations"}
FORBIDDEN_TERMS = {
    "company_rating",
    "stock_rating",
    "stock_price",
    "valuation",
    "watchlist",
    "strategy",
}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def is_r2b_path(path: str) -> bool:
    lowered = path.lower()
    parts = lowered.split("/")
    basename = parts[-1]
    if lowered.startswith(FORBIDDEN_PREFIXES):
        return False
    if any(part in FORBIDDEN_COMPONENTS for part in parts[:-1]):
        return False
    if basename in {"api.py", "database.py", "db.py", "router.py", "routes.py"}:
        return False
    if any(term in lowered for term in FORBIDDEN_TERMS):
        return False
    return path in ALLOWED_EXACT_PATHS or path.startswith(ALLOWED_PREFIXES)


@pytest.mark.parametrize(
    "path",
    [
        "artifacts/research_projects/v2_1/schema/definitions_v2_2.schema.json",
        "artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck/versions/v0.2.0.json",
        "artifacts/research_projects/v2_1/evidence/artifacts/evidence_artifact:abc.json",
        "src/stock_research/research_project_v2_1/diff.py",
        "tests/test_research_project_v2_1_r2b_schema.py",
        "docs/research_operating_layer_v2_r2b_ai_compute_pcb_checkpoint.md",
    ],
)
def test_r2b_scope_allows_only_approved_ai_pcb_paths(path: str) -> None:
    assert is_r2b_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "artifacts/research_projects/v2/index/research_project_index_v2.json",
        "artifacts/theme_decomposition/theme.json",
        "artifacts/technology_industry_catalog/catalog.json",
        "artifacts/research_projects/v2_1/projects/high_end_medical_device_industry_bottleneck/versions/v0.2.0.json",
        "artifacts/research_projects/v2_1/projects/humanoid_robot_industry_bottleneck/versions/v0.2.0.json",
        "artifacts/research_projects/v2_1/projects/new_energy_storage_industry_bottleneck/versions/v0.2.0.json",
        "dashboard/src/App.tsx",
        "src/stock_research/dashboard/api.py",
        "src/stock_research/research_project_v2_1/api.py",
        "src/stock_research/research_project_v2_1/database.py",
        "src/stock_research/research_project_v2_1/company_rating.py",
        "artifacts/research_projects/v2_1/stock_rating/output.json",
        "artifacts/research_projects/v2_1/watchlist/output.json",
        "artifacts/research_projects/v2_1/strategy/output.json",
    ],
)
def test_r2b_scope_rejects_v1_downstream_and_non_ai_pilot_paths(path: str) -> None:
    assert not is_r2b_path(path)


def test_r2b_phase1_seed_is_an_ancestor_and_approved_commits_are_explicit() -> None:
    assert _git("merge-base", "--is-ancestor", R2B_PHASE1_SEED, "HEAD").returncode == 0
    assert len(APPROVED_R2B_COMMITS) == len(set(APPROVED_R2B_COMMITS))
    assert all(len(commit) == 40 for commit in APPROVED_R2B_COMMITS)
    for commit in APPROVED_R2B_COMMITS:
        assert _git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0


def test_every_approved_r2b_commit_stays_inside_scope() -> None:
    changed: set[str] = set()
    for commit in APPROVED_R2B_COMMITS:
        result = _git("diff-tree", "--no-commit-id", "--name-only", "-r", commit)
        changed.update(path for path in result.stdout.splitlines() if path)
    assert not [path for path in sorted(changed) if not is_r2b_path(path)]
