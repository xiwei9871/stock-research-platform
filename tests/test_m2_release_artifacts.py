"""Machine acceptance for M2 release artifacts.

Guarantees every committed .json deliverable parses, required artifacts
exist, and SHA256 manifests actually match their files. Runnable against
the GitHub checkout alone (no DB, no credentials).
"""
import hashlib
import json
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs" / "research_upgrade" / "implementation" / "m2"

PREFLIGHT_REQUIRED = [
    "INTEGRATION_MANIFEST.md", "PRODUCTION_READONLY_ASSESSMENT.md",
    "INTEGRITY_GATE_ACCEPTANCE.json", "EOD_TRANSACTION_AND_DEPENDENCY_MAP.md",
    "EOD_E2E_TEST_REPORT.md", "M2_T_RELEASE_PACKAGE.md",
    "M2_T_PRODUCTION_RUNBOOK.md", "M2_F_RELEASE_PACKAGE.md",
    "M2_F_PRODUCTION_RUNBOOK.md", "FINVER_CONCURRENCY_AND_REPLAY_TESTS.json",
    "RESOURCE_BACKUP_ROLLBACK_GATE.md", "M2_APPROVAL_MATRIX.md",
    "REGRESSION_DIFF.md", "FINAL_GATE.json", "SHA256_MANIFEST.txt",
]

PRELAUNCH_REQUIRED = [
    "PRODUCTION_BACKUP_DISCOVERY.md", "BACKUP_OPTIONS_COMPARISON.md",
    "RECOMMENDED_BACKUP_ARCHITECTURE.md", "BACKUP_RESOURCE_AND_CAPACITY_PLAN.md",
    "RESTORE_DRILL_REPORT.md", "BACKUP_RECOVERY_GATE.json",
    "M2_RELEASE_PACKAGE_CORRECTIONS.md", "BACKFILL_EXECUTOR_SAFETY_REPORT.md",
    "BACKFILL_ADVERSARIAL_TESTS.json", "FINVER_WRITER_READINESS.md",
    "INTEGRITY_GATE_FINAL.json", "M2_APPROVAL_MATRIX_REVISED.md",
    "REGRESSION_DIFF.md", "FINAL_GATE.json", "SHA256_MANIFEST.txt",
]

VALID_GATE_STATES = {
    "PASS", "PASS_WITH_CONDITIONS", "BLOCKED", "FAIL",
    "M2_PREFLIGHT_PASS", "M2_PREFLIGHT_PASS_WITH_CONDITIONS",
    "M2_PREFLIGHT_BLOCKED", "M2_PRELAUNCH_PASS", "M2_PRELAUNCH_CONDITIONAL",
    "M2_PRELAUNCH_BLOCKED_BACKUP", "M2_PRELAUNCH_BLOCKED_CODE",
    "READY", "DEGRADED", "LEGACY_READY", "V2_READY",
}


def _json_files():
    return sorted(DOCS.rglob("*.json"))


def test_all_json_artifacts_valid():
    bad = []
    for f in _json_files():
        try:
            json.loads(f.read_text())
        except Exception as e:  # noqa: BLE001
            bad.append(f"{f.name}: {e}")
    assert not bad, f"invalid_json={len(bad)}: {bad}"


@pytest.mark.parametrize("name", PREFLIGHT_REQUIRED)
def test_preflight_required_artifact(name):
    assert (DOCS / "preflight" / name).is_file(), f"missing_required_artifact={name}"


@pytest.mark.parametrize("name", PRELAUNCH_REQUIRED)
def test_prelaunch_required_artifact(name):
    assert (DOCS / "prelaunch" / name).is_file(), f"missing_required_artifact={name}"


def test_sha256_manifests_match():
    """Recompute every manifest entry; zero mismatches allowed."""
    mismatches = []
    for manifest in DOCS.rglob("SHA256_MANIFEST.txt"):
        for line in manifest.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            digest, _, path = line.partition("  ")
            repo_root = DOCS.parents[3]
            p = Path(path) if Path(path).is_absolute() else repo_root / path
            if not p.is_file():
                p = manifest.parent / Path(path).name
            if not p.is_file():
                mismatches.append(f"missing:{path}")
                continue
            actual = hashlib.sha256(p.read_bytes()).hexdigest()
            if actual != digest:
                mismatches.append(f"hash:{path}")
    assert not mismatches, f"manifest_mismatch={len(mismatches)}: {mismatches[:5]}"


def test_final_gate_states_consistent():
    """FINAL_GATE.json final_state must be a legal M2 state; gates must
    carry legal statuses; a BLOCKED gate forbids *_PASS final_state."""
    for fg in DOCS.rglob("FINAL_GATE.json"):
        doc = json.loads(fg.read_text())
        final = doc.get("final_state", "")
        assert final in VALID_GATE_STATES, f"{fg}: bad final_state {final}"
        blocked = [
            k for k, g in doc.get("gates", {}).items()
            if isinstance(g, dict) and g.get("status") == "BLOCKED"
        ]
        for k, g in doc.get("gates", {}).items():
            if isinstance(g, dict):
                assert g.get("status") in VALID_GATE_STATES, f"{fg}:{k} bad status"
        if blocked:
            assert "PASS" not in final or "BLOCKED" in final or "CONDITIONS" in final or "CONDITIONAL" in final, \
                f"{fg}: final_state {final} contradicts blocked gates {blocked}"
