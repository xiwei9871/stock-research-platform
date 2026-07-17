from __future__ import annotations

from functools import lru_cache
from pathlib import Path, PurePosixPath
import re
import subprocess

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCOPE_EVIDENCE = Path("/private/tmp/research_project_v2_changed_files.txt")
EXPECTED_COMMIT_COUNT = 26
EXPECTED_PATH_COUNT = 58

APPROVED_R1_COMMITS = (
    "6043d723e858bc462e620a38cc802fc0e0e7b5dc",
    "ef48b43aed326b6b2e9138ae7e2d0dd1c56386d5",
    "d91f31807547ba6ee8f410c6f59558b705d9a842",
    "09fa0360f7c96a19e2c4cf92e725fc6d933e5a7c",
    "9d71080d9f0761464b4e2d91a558a17cf27ad490",
    "a05b343d6ffbed283053775d5aa65f7b892ad0b9",
    "8f1e12db1e83d228b201b64e813a3da8f3671c2d",
    "43596e133af74f50db035a2fd6fbe6c7dc123b31",
    "5adeb2391e6abd953a81c7559ba726f727b61449",
    "a069938cc76795a39e169282b14d53cef7bcdc13",
    "50e60ff5e6e89b7a0ad1008805ec010d870d12a8",
    "7ce916e1a75682eed4b4dbf7d18e43a316af2fa8",
    "03f65f44f0340bd3799a813a2eea613cd4b10bed",
    "5be81275918783ddacce8c52e582cb42c53f7ee5",
    "981537ae2ebbd9c4c677576ce2acfd0d086a0283",
    "c65bb20cea8cbc1147d3b43b5d47e1b07b03fe06",
    "1fa470f266a332657bb999a7fadd2313533a28cd",
    "278a242ee7f22738164241d362b1110d6f3bce82",
    "a4d0b914628a79fd00f7e0d7e02d5ebc70668b4d",
    "b4bc5cafe8ac28cb0d94a8cface305d642b5cd0c",
    "e81aae007a29f31defa5454b88299f9408c6bf67",
    "39c35aa1fc8430d00660e67cdb8d79039de98817",
    "c6720431fa6ac7cee18653bfc4d933acced654a7",
    "85c07904469d0b6aab90291a1433b16c9fc89b6c",
    "f9e07988496429786367ef4b21f8e265fbe21a94",
    "6fa4074791bbe90782fc4ee9151dc791d0d753ce",
)

PACKAGE_MODULES = {
    f"src/stock_research/research_project_v2/{name}.py"
    for name in (
        "__init__",
        "canonical",
        "cli",
        "diff",
        "errors",
        "gates",
        "layout",
        "loader",
        "references",
        "semantic",
        "summary",
    )
}

SCHEMA_PATHS = {
    f"artifacts/research_projects/v2/schema/{name}_v2.schema.json"
    for name in (
        "definitions",
        "research_event",
        "research_project_identity",
        "research_project_index",
        "research_version",
    )
}

PROJECT_SLUGS = {
    "ai_compute_pcb_value_migration",
    "high_end_medical_device_commercialization",
    "humanoid_robot_scale_up_bottlenecks",
    "new_energy_storage_route_competition",
}

PROJECT_REQUIRED_PATHS = {
    f"artifacts/research_projects/v2/projects/{slug}/{relative}"
    for slug in PROJECT_SLUGS
    for relative in (
        "project.json",
        "version_manifest.jsonl",
        "versions/v0.1.0.json",
    )
}

PROJECT_ALLOWED_PATHS = PROJECT_REQUIRED_PATHS | {
    f"artifacts/research_projects/v2/projects/{slug}/events/events.jsonl"
    for slug in PROJECT_SLUGS
}

FIXTURE_PATHS = {
    "artifacts/research_projects/v2/fixtures/valid/research_design_minimal_v2.json",
    "artifacts/research_projects/v2/fixtures/invalid/company_capture_in_research_design.json",
    "artifacts/research_projects/v2/fixtures/invalid/duplicate_claim_id.json",
    "artifacts/research_projects/v2/fixtures/invalid/evidence_assessment_in_research_design.json",
    "artifacts/research_projects/v2/fixtures/invalid/hash_mismatch.json",
    "artifacts/research_projects/v2/fixtures/invalid/missing_reference.json",
    "artifacts/research_projects/v2/fixtures/invalid/premature_supported_claim.json",
    "artifacts/research_projects/v2/fixtures/invalid/question_dependency_cycle.json",
    "artifacts/research_projects/v2/fixtures/invalid/unmarked_causal_cycle.json",
    "artifacts/research_projects/v2/fixtures/invalid/invalid_version_manifest/projects/fixture/project.json",
    "artifacts/research_projects/v2/fixtures/invalid/invalid_version_manifest/projects/fixture/version_manifest.jsonl",
    "artifacts/research_projects/v2/fixtures/invalid/invalid_version_manifest/projects/fixture/versions/v0.1.0.json",
}

EXACT_ALLOWED = {
    "pyproject.toml",
    "src/stock_research/cli.py",
    "artifacts/research_projects/v2/index/research_project_index_v2.json",
    "docs/research_operating_layer_v2_goal_and_roadmap.md",
    "docs/research_operating_layer_v2_r1.md",
} | SCHEMA_PATHS | PROJECT_ALLOWED_PATHS | FIXTURE_PATHS

REQUIRED_PATHS = {
    "pyproject.toml",
    "src/stock_research/cli.py",
    "artifacts/research_projects/v2/index/research_project_index_v2.json",
    "docs/research_operating_layer_v2_goal_and_roadmap.md",
    "docs/research_operating_layer_v2_r1.md",
    "tests/test_research_project_v2_scope_guard.py",
} | PACKAGE_MODULES | SCHEMA_PATHS | PROJECT_REQUIRED_PATHS

PACKAGE_PATTERN = re.compile(
    r"^src/stock_research/research_project_v2/[a-z_]+\.py$"
)
TEST_PATTERN = re.compile(r"^tests/test_research_project_v2_[a-z_]+\.py$")
PRODUCTION_MIGRATION_FILENAME = re.compile(
    r"(^|/)(?:v?\d{3,}[^/]*\.(?:sql|py)|[^/]*migration[^/]*\.(?:sql|py))$",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _compute_changed_files() -> tuple[str, ...]:
    assert len(APPROVED_R1_COMMITS) == EXPECTED_COMMIT_COUNT
    assert all(re.fullmatch(r"[0-9a-f]{40}", commit) for commit in APPROVED_R1_COMMITS)
    changed: set[str] = set()
    for commit in APPROVED_R1_COMMITS:
        result = subprocess.run(
            ["git", "show", "--pretty=", "--name-only", commit],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"approved R1 commit is unavailable: {commit}; CI must fetch full history "
            "(for GitHub Actions use fetch-depth: 0). git said: {result.stderr.strip()}"
        )
        changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return tuple(sorted(changed))


def _optional_evidence_paths() -> list[str] | None:
    if not SCOPE_EVIDENCE.is_file():
        return None
    return [
        line.strip()
        for line in SCOPE_EVIDENCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _changed_files() -> list[str]:
    computed = list(_compute_changed_files())
    assert len(computed) == EXPECTED_PATH_COUNT, (
        f"computed R1 scope has {len(computed)} paths; expected {EXPECTED_PATH_COUNT}; "
        "check the approved commit list for truncation or unrelated commits"
    )
    missing_required = sorted(REQUIRED_PATHS - set(computed))
    assert missing_required == [], (
        f"computed R1 scope is missing required paths: {missing_required}"
    )
    evidence = _optional_evidence_paths()
    if evidence is not None:
        assert evidence == computed, (
            f"optional evidence {SCOPE_EVIDENCE} does not match computed R1 commit union"
        )
    return computed


def _is_allowed(path: str) -> bool:
    return (
        path in EXACT_ALLOWED
        or PACKAGE_PATTERN.fullmatch(path) is not None
        or TEST_PATTERN.fullmatch(path) is not None
    )


def _is_forbidden(path: str) -> bool:
    normalized = PurePosixPath(path).as_posix()
    lowered = normalized.casefold()
    if lowered.startswith(
        (
            "artifacts/theme_decomposition/",
            "artifacts/technology_industry_catalog/",
            "dashboard/",
            "src/stock_research/dashboard/",
        )
    ):
        return True
    if lowered == "src/stock_research/theme_research_db_schema.py":
        return True
    components = {component.casefold() for component in PurePosixPath(path).parts}
    if components & {
        "alembic",
        "api",
        "database",
        "db",
        "migration",
        "migrations",
        "route",
        "routes",
    }:
        return True
    return lowered.endswith(".sql") or lowered.endswith("/schema.sql")


def _assert_paths_allowed(changed: list[str]) -> None:
    forbidden = [path for path in changed if _is_forbidden(path)]
    outside_allowlist = [path for path in changed if not _is_allowed(path)]
    migration_files = [
        path for path in changed if PRODUCTION_MIGRATION_FILENAME.search(path)
    ]
    assert forbidden == [], f"R1 scope contains forbidden paths: {forbidden}"
    assert outside_allowlist == [], (
        f"R1 scope contains paths outside the precise allowlist: {outside_allowlist}"
    )
    assert migration_files == [], (
        f"R1 contains production migration filenames: {migration_files}"
    )


def test_r1_changed_files_stay_inside_the_research_project_v2_scope() -> None:
    _assert_paths_allowed(_changed_files())


def test_missing_optional_evidence_uses_computed_commit_union(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "test_research_project_v2_scope_guard.SCOPE_EVIDENCE",
        tmp_path / "missing-evidence.txt",
    )
    assert len(_changed_files()) == EXPECTED_PATH_COUNT


def test_truncated_optional_evidence_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "truncated-evidence.txt"
    evidence.write_text("pyproject.toml\n", encoding="utf-8")
    monkeypatch.setattr(
        "test_research_project_v2_scope_guard.SCOPE_EVIDENCE", evidence
    )
    with pytest.raises(AssertionError, match="does not match computed R1 commit union"):
        _changed_files()


@pytest.mark.parametrize(
    "path",
    (
        "artifacts/research_projects/v2/fixtures/invalid/database/schema.sql",
        "artifacts/research_projects/v2/fixtures/invalid/api/routes.py",
    ),
)
def test_forbidden_database_and_api_fixture_paths_are_rejected(path: str) -> None:
    with pytest.raises(AssertionError, match="forbidden paths"):
        _assert_paths_allowed([path])
