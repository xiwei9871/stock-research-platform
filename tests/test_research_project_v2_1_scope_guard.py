from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# R2A work was developed on a shared integration branch.  The attribution
# boundary is therefore an explicit, reviewed set of commits rather than a
# base..HEAD range, which would silently absorb unrelated concurrent work.
APPROVED_R2A_COMMITS = (
    "93f825717964535494a7aaebe95c0e0ef5b7f312",
    "2aa815746fe1479aa8587e9272d553828570f477",
    "70d4c8ba20dd39a43f2513c28472349b7937a52a",
    "7a7c93d05c2399c3b3ca48dcb8d5e1f1d4fe41dd",
    "6805d805acb0e714a6f7ac22142b81333a599064",
    "53ddf7749f5917fd272c87d7949546722e39e585",
    "69994a53c9e835fdd22f58413cca39f0bd293981",
    "35b7797547b1f7e46cbfed1a7527eb033b834711",
    "7c6a19d30a3141e9aad6a3321aceb8b75b1745f3",
    "242d397fdd4c0cabb1899c5166dcbbc5aaea6ad7",
    "a3767b4f15d8aa499435c4d2401e763e96c24bee",
    "f0183757973e53594d50ebd86553d69291a423e5",
    "905320995a68b480c5c77d56ca20ca626d7458aa",
    "3e60078835184a3f6ae1694f96a8e54ba83e07d9",
    "98bea47f4b3413fce11d00fecda5996f847ba699",
    "115e65956baabdc42429c86ea5a5be565f38d809",
    "79d7267ef37d38849f265dc93f92446fc34eb491",
    "4abcc4fccaf6e77124f971e40ee37bd4744a8202",
    "9001524e07f7f8bc8c36bbe7a4295459d403744a",
    "af128d69db79f60720dc0dc78eac4765b476fd4c",
    "2aa28ccd0c9fc2360d2e989cabf9aa5a9c18072c",
    "7802f53739e02bcd56bcf45670d188ed449ff31d",
    "011f2f86f941bd19e8be90b3bee99e8959fa6c04",
    "2894173775887cd202f31206fa4c95f8c5beaf10",
    "57db490ad09ee0ccb1f1430ede8c234a5f836c47",
    "66bec1f822f8c907471a540bd4084a931075eff3",
    "2eec08ac27f1d2405a967d39fcc3469fbac7fe2a",
    "29cd6c9c0c20b9e92bcbc75f633e1bd1c87e0da9",
    "7b243be0881e3448816f91689e9c100718ed8bcd",
    "d6700742895d9029bb2ccd58ad12b638b4700601",
    "721821db841ae797798e1348abc2bb138696ff25",
    "8b7cefdf6637b55daf993f2c210ab654b0bab615",
    "559b276d52d758c40ee787044e224faf5920563e",
    "9b93076eb5cbeb07d88d89d79627251f7b0ada0e",
    "0fced6dd2f9eccb6a0ae34be5bc8e9d4ecfb4daa",
    "c4734789f9ec0f417da77952f2a1289b40fc6c3e",
    "d7058a6e100dab9ba88d6dd0e86e728b49f3a0ca",
    "18af7eb3fcfdc7d996a5fc3653d1487b0dc83bcc",
    "0b65f8ac6a7c6b6c1357bd4d86f4c5ba86cc5442",
    "b7d9cb89f2473a81f4a66493513bda7546dc4b08",
    "1d4d7ef84cfcc9105f467192b39cfc2a58a2f150",
    "e1a81d98ab57c865be551541c1b4f94f5b75dec2",
    "fd1ac650b5bf894303d4245f06705deead58f9bb",
    "e6d7b39cfdfd3170eaabfac3e9a1d0e11773b139",
    "15ce5fec1b1af26c9a6560db971e3d9a62892f93",
    "f495d9226564d35908491722f57faead513f8f40",
    "6bf3098b831ef9eba31a6cf4d57830a01560dab4",
    "2117578c332113325b4a8614cff5e4b436123e0d",
    "1318ea284edad80c97ce1f71d4a6d89b14e9f726",
    "7ded7fb989c4ac23eeece0902599ab63c8575b8b",
    "7cf1a0a86a522b3dbcb868807cc609ff58f20010",
    "bf34131bd1d5be14fee557d4ddd91ee3bb6a8c2c",
    "0f886f1c0c4793872db8f59659cdc79b6d4a5eea",
    "128625f9c1bf4cd4a5f0c209b6424f1b0e8aaa23",
    "2607cb332583c0db86dfbcae8bb73b1e31c658d0",
    "14ee82d838f61e770ac14f1abb8a1c830344fe53",
)

EXCLUDED_CONCURRENT_COMMITS = {
    "d8cdfbf",
    "c6e1b8e",
    "e0d8ebd",
}

ALLOWED_EXACT_PATHS = {
    "src/stock_research/cli.py",
    "docs/superpowers/specs/2026-07-18-research-layer-separation-design.md",
    "docs/superpowers/plans/2026-07-18-industry-evidence-acquisition-r2a.md",
    "docs/research_operating_layer_v2_goal_and_roadmap.md",
    "docs/research_operating_layer_v2_r2a.md",
}
ALLOWED_PREFIXES = (
    "artifacts/research_projects/v2_1/",
    "src/stock_research/research_project_v2_1/",
)
FORBIDDEN_PREFIXES = (
    "artifacts/research_projects/v2/",
    "artifacts/theme_decomposition/",
    "artifacts/technology_industry_catalog/",
    "dashboard/",
    "src/stock_research/dashboard/",
)
FORBIDDEN_PATH_PARTS = (
    "/api/",
    "/migrations/",
    "/migration/",
    "/database/",
    "company_rating",
    "stock_rating",
    "company_capture",
    "stock_evaluation",
)
FORBIDDEN_FILE_NAMES = {
    "api.py",
    "routes.py",
    "database_schema.py",
    "db_schema.py",
}


def is_r2a_path(path: str) -> bool:
    normalized = f"/{path.lower()}"
    if path.startswith(FORBIDDEN_PREFIXES):
        return False
    # Negative fixtures are approved support files whose payloads prove that
    # downstream research layers are rejected; they are not runnable artifacts.
    if path.startswith("artifacts/research_projects/v2_1/fixtures/invalid/"):
        return True
    if path.lower().rsplit("/", 1)[-1] in FORBIDDEN_FILE_NAMES:
        return False
    if any(part in normalized for part in FORBIDDEN_PATH_PARTS):
        return False
    if path in ALLOWED_EXACT_PATHS:
        return True
    if path.startswith(ALLOWED_PREFIXES):
        return True
    return path.startswith("tests/test_research_project_v2_1_") and path.endswith(".py")


def changed_paths_for_approved_commits() -> set[str]:
    paths: set[str] = set()
    for commit in APPROVED_R2A_COMMITS:
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit,
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        paths.update(line for line in result.stdout.splitlines() if line)
    return paths


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
        "docs/research_operating_layer_v2_r2a.md",
    ],
)
def test_scope_guard_allows_only_planned_r2a_paths(path: str) -> None:
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
        "src/stock_research/research_project_v2_1/api.py",
        "src/stock_research/research_project_v2_1/api/routes.py",
        "src/stock_research/research_project_v2_1/routes.py",
        "src/stock_research/research_project_v2_1/database_schema.py",
        "src/stock_research/research_project_v2_1/db_schema.py",
        "src/stock_research/research_project_v2_1/migrations/001.sql",
        "src/stock_research/research_project_v2_1/company_rating.py",
        "src/stock_research/research_project_v2_1/stock_rating.py",
        "artifacts/research_projects/v2_1/company_capture/project.json",
        "artifacts/research_projects/v2_1/stock_evaluation/project.json",
        "tests/test_research_project_v2_storage.py",
        "docs/superpowers/plans/unrelated.md",
    ],
)
def test_scope_guard_rejects_r1_and_out_of_scope_paths(path: str) -> None:
    assert not is_r2a_path(path)


def test_approved_commit_list_is_full_sha_unique_and_excludes_shared_work() -> None:
    assert len(APPROVED_R2A_COMMITS) == len(set(APPROVED_R2A_COMMITS))
    assert all(len(commit) == 40 for commit in APPROVED_R2A_COMMITS)
    assert not any(
        commit.startswith(excluded)
        for commit in APPROVED_R2A_COMMITS
        for excluded in EXCLUDED_CONCURRENT_COMMITS
    )


def test_every_path_attributed_to_approved_r2a_commits_is_in_scope() -> None:
    changed_paths = changed_paths_for_approved_commits()
    assert changed_paths
    assert not [path for path in sorted(changed_paths) if not is_r2a_path(path)]
