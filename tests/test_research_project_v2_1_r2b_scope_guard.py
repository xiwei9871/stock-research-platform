from __future__ import annotations

import subprocess
import json
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
R2B_PHASE1_SEED = "dec9187"
APPROVED_R2B_COMMITS = (
    "0fb8997dc09bf89cbbc9116a68c03dc3885eef86",
    "0577656e5f3c981d9ecbb1a56c129b02a34099f1",
    "fa516b9b10e61d2b0f88c59b6da7a11a933002d6",
    "560d700d970ac281f2274faa362a86c4ac7ed1c6",
    "bc0f56ba8f39b54bd05f075bdaf35451c4e495a2",
    "db2ad5320d3a3debd816ed3c8a760f8cc6c7d709",
)
R2B_CLOSURE_SEED = "db2ad5320d3a3debd816ed3c8a760f8cc6c7d709"
R2B_CLOSURE_END = "fd057e20ca1d81129ff39f0a253fe122acca99c2"
R2B_CLOSURE_FILES = {"tests/test_research_project_v2_1_r2b_scope_guard.py"}
ACQUISITION_RECOVERY_PHASE_A_SEED = "fd057e20ca1d81129ff39f0a253fe122acca99c2"
ACQUISITION_RECOVERY_PHASE_A_END = "d8b3101149408bfb92cd3733eb737e3ba677ea47"
ACQUISITION_RECOVERY_PHASE_B_END = "d76c95f"
ACQUISITION_PHASE_C_END = "34210fb"
STAGE_A_ACQUISITION_BASELINE = ACQUISITION_PHASE_C_END
STAGE_A_ACQUISITION_END = "ae4e70e"
STAGE_A_SCOPE_CORRECTION_BASELINE = STAGE_A_ACQUISITION_END
STAGE_A_SCOPE_CORRECTION_END = "7280ba71b1694f1ac5938d8be258b9803dfc285e"
INDUSTRY_COGNITION_BASELINE = STAGE_A_SCOPE_CORRECTION_END
INDUSTRY_COGNITION_END = "989b1258c54000990349692f4b07b968e8eaabd5"
EVIDENCE_GAP_REVIEW_BASELINE = INDUSTRY_COGNITION_END
EVIDENCE_GAP_REVIEW_END = "16855be"
ACQUISITION_RECOVERY_PHASE_A_PATHS = {
    "artifacts/research_projects/v2_1/acquisition/diagnostics/r2b_external_acquisition_phase_a_2026-07-20.json",
    "docs/research_operating_layer_v2_r2b_external_acquisition_recovery_phase_a.md",
    "tests/test_research_project_v2_1_r2b_scope_guard.py",
}

ALLOWED_EXACT_PATHS = {
    "docs/research_operating_layer_v2_r2b_plan.md",
    "docs/research_operating_layer_v2_r2b_schema_extension_proposal.md",
    "src/stock_research/cli.py",
    "tests/test_research_project_v2_1_schema.py",
    "tests/test_research_project_v2_1_pilots.py",
    "tests/test_research_project_v2_1_cli.py",
    "tests/test_research_project_v2_1_scope_guard.py",
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


def test_r2b_closure_amendments_only_touch_the_scope_guard() -> None:
    result = _git("diff", "--name-only", f"{R2B_CLOSURE_SEED}..{R2B_CLOSURE_END}")
    changed = {path for path in result.stdout.splitlines() if path}
    assert changed <= R2B_CLOSURE_FILES


def test_acquisition_recovery_phase_a_only_adds_diagnostics_and_governance() -> None:
    assert (
        _git("merge-base", "--is-ancestor", ACQUISITION_RECOVERY_PHASE_A_END, "HEAD").returncode
        == 0
    )
    result = _git(
        "diff", "--name-only", f"{ACQUISITION_RECOVERY_PHASE_A_SEED}..{ACQUISITION_RECOVERY_PHASE_A_END}"
    )
    changed = {path for path in result.stdout.splitlines() if path}
    assert changed <= ACQUISITION_RECOVERY_PHASE_A_PATHS


def test_acquisition_recovery_phase_b_uses_the_machine_readable_exact_allowlist() -> None:
    allowlist_path = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/acquisition/phase_b_exact_allowlist.json"
    )
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == ACQUISITION_RECOVERY_PHASE_A_END
    allowed = set(payload["paths"])
    assert len(allowed) == len(payload["paths"])
    assert (
        _git("merge-base", "--is-ancestor", ACQUISITION_RECOVERY_PHASE_B_END, "HEAD").returncode
        == 0
    )
    result = _git(
        "diff",
        "--name-only",
        f"{ACQUISITION_RECOVERY_PHASE_A_END}..{ACQUISITION_RECOVERY_PHASE_B_END}",
    )
    changed = {path for path in result.stdout.splitlines() if path}
    monitored_prefixes = (
        "artifacts/research_projects/v2_1/",
        "src/stock_research/research_project_v2_1/",
        "tests/test_research_project_v2_1_",
        "docs/research_operating_layer_v2_r2b_external_acquisition_",
        "docs/superpowers/plans/2026-07-20-r2b-external-acquisition-",
    )
    monitored = {path for path in changed if path.startswith(monitored_prefixes)}
    assert monitored <= allowed
    assert not any(
        path.startswith(tuple(payload["forbidden_prefixes"])) for path in changed
    )


def test_acquisition_phase_c_uses_a_separate_exact_allowlist() -> None:
    allowlist_path = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/acquisition/phase_c_exact_allowlist.json"
    )
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == ACQUISITION_RECOVERY_PHASE_B_END
    allowed = set(payload["paths"])
    assert len(allowed) == len(payload["paths"])
    assert (
        _git("merge-base", "--is-ancestor", ACQUISITION_PHASE_C_END, "HEAD").returncode
        == 0
    )
    result = _git(
        "diff",
        "--name-only",
        f"{ACQUISITION_RECOVERY_PHASE_B_END}..{ACQUISITION_PHASE_C_END}",
    )
    changed = {path for path in result.stdout.splitlines() if path}
    assert changed <= allowed
    assert not any(
        path.startswith(tuple(payload["forbidden_prefixes"])) for path in changed
    )


def test_stage_a_acquisition_uses_a_separate_exact_allowlist() -> None:
    allowlist_path = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/acquisition/stage_a_exact_allowlist.json"
    )
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == STAGE_A_ACQUISITION_BASELINE
    allowed = set(payload["paths"])
    assert len(allowed) == len(payload["paths"])
    assert (
        _git("merge-base", "--is-ancestor", STAGE_A_ACQUISITION_END, "HEAD").returncode
        == 0
    )
    result = _git(
        "diff",
        "--name-only",
        f"{STAGE_A_ACQUISITION_BASELINE}..{STAGE_A_ACQUISITION_END}",
    )
    changed = {path for path in result.stdout.splitlines() if path}
    assert changed <= allowed
    assert not any(
        path.startswith(tuple(payload["forbidden_prefixes"])) for path in changed
    )


def test_stage_a_scope_correction_uses_an_exact_append_only_allowlist() -> None:
    allowlist_path = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/governance/stage_a_scope_correction_exact_allowlist.json"
    )
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == STAGE_A_SCOPE_CORRECTION_BASELINE
    allowed = set(payload["paths"])
    assert len(allowed) == len(payload["paths"])
    original_checkpoint = (
        "artifacts/research_projects/v2_1/acquisition/checkpoints/"
        "acquisition_checkpoint:a5f7627d8726c9405ba67a75.json"
    )
    assert original_checkpoint not in allowed

    assert (
        _git("merge-base", "--is-ancestor", STAGE_A_SCOPE_CORRECTION_END, "HEAD").returncode
        == 0
    )
    result = _git(
        "diff",
        "--name-only",
        f"{STAGE_A_SCOPE_CORRECTION_BASELINE}..{STAGE_A_SCOPE_CORRECTION_END}",
    )
    changed = {path for path in result.stdout.splitlines() if path}
    assert changed <= allowed
    assert not any(
        path.startswith(tuple(payload["forbidden_prefixes"])) for path in changed
    )


def test_industry_cognition_baseline_uses_an_exact_read_only_allowlist() -> None:
    allowlist_path = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/governance/industry_cognition_baseline_exact_allowlist.json"
    )
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == INDUSTRY_COGNITION_BASELINE
    allowed = set(payload["paths"])
    assert len(allowed) == len(payload["paths"])

    result = _git(
        "diff",
        "--name-only",
        f"{INDUSTRY_COGNITION_BASELINE}..{INDUSTRY_COGNITION_END}",
    )
    changed = {path for path in result.stdout.splitlines() if path}
    assert changed <= allowed
    assert not any(
        path.startswith(tuple(payload["forbidden_prefixes"])) for path in changed
    )
    assert not any(
        token in path.lower()
        for path in changed
        for token in ("company_rating", "stock_rating", "valuation", "portfolio", "strategy")
    )


def test_evidence_gap_review_uses_an_exact_offline_read_only_allowlist() -> None:
    allowlist_path = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/governance/evidence_gap_review_exact_allowlist.json"
    )
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == EVIDENCE_GAP_REVIEW_BASELINE
    allowed = set(payload["paths"])
    assert len(allowed) == len(payload["paths"])

    assert _git("merge-base", "--is-ancestor", EVIDENCE_GAP_REVIEW_END, "HEAD").returncode == 0
    result = _git("diff", "--name-only", f"{EVIDENCE_GAP_REVIEW_BASELINE}..{EVIDENCE_GAP_REVIEW_END}")
    changed = {path for path in result.stdout.splitlines() if path}
    assert changed <= allowed
    assert not any(
        path.startswith(tuple(payload["forbidden_prefixes"])) for path in changed
    )
    immutable_inputs = {
        "artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_package_v1.json",
        "artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_audit_v1.json",
        "artifacts/research_projects/v2_1/reports/ai_pcb_industry_cognition_report_v1.md",
        "artifacts/research_projects/v2_1/acquisition/checkpoints/acquisition_checkpoint:a5f7627d8726c9405ba67a75.json",
    }
    assert not changed.intersection(immutable_inputs)
