from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path

from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_import import NormalizedThemeResearchPackage


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "theme_research_checkpoint_import_guard.py"
)
SPEC = importlib.util.spec_from_file_location(
    "theme_research_checkpoint_import_guard",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
evaluate_restore_gate = MODULE.evaluate_restore_gate
build_additive_restore_package = MODULE.build_additive_restore_package
execute_additive_restore = MODULE.execute_additive_restore


EXISTING_THEME_IDS = {
    "ai_power_value_capture_v1",
    "humanoid_robotics_head_to_toe_v1",
}
EXPECTED_THEME_IDS = EXISTING_THEME_IDS | {
    f"checkpoint_theme_{index:02d}" for index in range(1, 24)
}
FAMILIES = (
    "themes",
    "nodes",
    "sources",
    "theme_sources",
    "claims",
    "claim_sources",
    "claim_nodes",
    "assessments",
    "assessment_evidence",
    "company_mappings",
    "mapping_evidence_items",
    "company_mapping_evidence",
)


def _safe_diff() -> dict:
    missing = sorted(EXPECTED_THEME_IDS - EXISTING_THEME_IDS)
    families = {
        family: {
            "insert": missing if family == "themes" else [],
            "update": [],
            "deactivate": [],
            "no_change": sorted(EXISTING_THEME_IDS) if family == "themes" else [],
        }
        for family in FAMILIES
    }
    return {
        "has_changes": True,
        "summary": {
            "insert": len(missing),
            "update": 0,
            "deactivate": 0,
            "no_change": len(EXISTING_THEME_IDS),
        },
        "families": families,
    }


def test_restore_gate_allows_exactly_23_inserts_without_mutations() -> None:
    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=_safe_diff(),
    )

    assert result["allowed"] is True
    assert result["violations"] == []
    assert result["theme_counts"] == {
        "expected": 25,
        "current": 2,
        "insert": 23,
        "update": 0,
        "deactivate": 0,
    }


def test_restore_gate_rejects_any_update() -> None:
    diff = deepcopy(_safe_diff())
    diff["families"]["nodes"]["update"] = ["existing-node"]

    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=diff,
    )

    assert result["allowed"] is False
    assert "updates_present:nodes:1" in result["violations"]


def test_restore_gate_rejects_any_deactivation() -> None:
    diff = deepcopy(_safe_diff())
    diff["families"]["sources"]["deactivate"] = ["existing-source"]

    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=diff,
    )

    assert result["allowed"] is False
    assert "deactivations_present:sources:1" in result["violations"]


def test_restore_gate_rejects_unexpected_current_theme_set() -> None:
    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids={"unexpected_theme"},
        semantic_diff=_safe_diff(),
    )

    assert result["allowed"] is False
    assert "current_theme_ids_mismatch" in result["violations"]


def test_restore_gate_rejects_wrong_expected_theme_count() -> None:
    result = evaluate_restore_gate(
        expected_theme_ids=set(sorted(EXPECTED_THEME_IDS)[:-1]),
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=_safe_diff(),
    )

    assert result["allowed"] is False
    assert "expected_theme_count:24" in result["violations"]


def _package(
    *,
    themes: list[dict],
    nodes: list[dict] | None = None,
    sources: list[dict] | None = None,
    theme_sources: list[dict] | None = None,
) -> NormalizedThemeResearchPackage:
    return NormalizedThemeResearchPackage.build(
        artifact_version="theme_decomposition_v1_6",
        themes=themes,
        nodes=nodes or [],
        sources=sources or [],
        theme_sources=theme_sources or [],
        claims=[],
        claim_sources=[],
        claim_nodes=[],
        assessments=[],
        assessment_evidence=[],
        company_mappings=[],
        mapping_evidence_items=[],
        company_mapping_evidence=[],
    )


def test_additive_restore_preserves_current_theme_and_adds_only_missing_theme() -> None:
    current_theme = {
        "theme_id": "existing",
        "theme_name": "production value",
        "content_sha256": "production-hash",
    }
    checkpoint_theme = {
        "theme_id": "existing",
        "theme_name": "newer checkpoint value",
        "content_sha256": "checkpoint-hash",
    }
    missing_theme = {
        "theme_id": "missing",
        "theme_name": "missing theme",
        "content_sha256": "missing-hash",
    }
    current = _package(themes=[current_theme])
    checkpoint = _package(themes=[checkpoint_theme, missing_theme])

    desired = build_additive_restore_package(
        current=current,
        checkpoint=checkpoint,
        expected_theme_ids={"existing", "missing"},
    )

    assert list(desired.themes) == [current_theme, missing_theme]


def test_additive_restore_rejects_cross_theme_identity_collision() -> None:
    current = _package(
        themes=[{"theme_id": "existing"}],
        sources=[{"source_id": "shared", "title": "production"}],
        theme_sources=[
            {"theme_id": "existing", "source_id": "shared", "link_reason": "manual"}
        ],
    )
    checkpoint = _package(
        themes=[{"theme_id": "existing"}, {"theme_id": "missing"}],
        sources=[{"source_id": "shared", "title": "checkpoint"}],
        theme_sources=[
            {"theme_id": "missing", "source_id": "shared", "link_reason": "manual"}
        ],
    )

    try:
        build_additive_restore_package(
            current=current,
            checkpoint=checkpoint,
            expected_theme_ids={"existing", "missing"},
        )
    except ValueError as exc:
        assert "sources:shared" in str(exc)
    else:
        raise AssertionError("expected an identity collision")


def test_execute_additive_restore_commits_guarded_merged_package(monkeypatch) -> None:
    current_themes = [
        {"theme_id": theme_id, "theme_name": f"production {theme_id}"}
        for theme_id in sorted(EXISTING_THEME_IDS)
    ]
    missing_themes = [
        {"theme_id": theme_id, "theme_name": f"checkpoint {theme_id}"}
        for theme_id in sorted(EXPECTED_THEME_IDS - EXISTING_THEME_IDS)
    ]
    current = _package(themes=current_themes)
    checkpoint = _package(
        themes=[
            {"theme_id": theme_id, "theme_name": f"newer {theme_id}"}
            for theme_id in sorted(EXISTING_THEME_IDS)
        ]
        + missing_themes
    )
    captured: dict = {}

    def fake_bootstrap(package, **kwargs):
        captured["package"] = package
        captured["kwargs"] = kwargs
        return {"status": "committed", "resulting_generation": 5}

    monkeypatch.setattr(MODULE, "bootstrap_package", fake_bootstrap)

    result = execute_additive_restore(
        current=current,
        checkpoint=checkpoint,
        expected_theme_ids=EXPECTED_THEME_IDS,
        actor_user_id="admin-id",
        actor_role="admin",
        expected_generation=4,
        idempotency_key="additive-import",
        runtime_service="runtime",
        approved_checkpoint_sha256=checkpoint.package_sha256,
        approved_database_sha256=current.package_sha256,
        approved_desired_sha256=build_additive_restore_package(
            current=current,
            checkpoint=checkpoint,
            expected_theme_ids=EXPECTED_THEME_IDS,
        ).package_sha256,
    )

    assert result["status"] == "committed"
    assert list(captured["package"].themes) == sorted(
        current_themes + missing_themes,
        key=lambda row: row["theme_id"],
    )
    assert captured["kwargs"]["expected_generation"] == 4
    assert captured["kwargs"]["service"] == "runtime"
    assert captured["kwargs"]["required_theme_inserts"] == 23
    assert captured["kwargs"]["forbid_updates"] is True
    assert captured["kwargs"]["forbid_deactivations"] is True


def test_execute_additive_restore_rejects_checkpoint_changed_after_preflight(
    monkeypatch,
) -> None:
    current = _package(
        themes=[{"theme_id": theme_id} for theme_id in sorted(EXISTING_THEME_IDS)]
    )
    checkpoint = _package(
        themes=[{"theme_id": theme_id} for theme_id in sorted(EXPECTED_THEME_IDS)]
    )
    monkeypatch.setattr(
        MODULE,
        "bootstrap_package",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("bootstrap must not run")
        ),
    )

    try:
        execute_additive_restore(
            current=current,
            checkpoint=checkpoint,
            expected_theme_ids=EXPECTED_THEME_IDS,
            actor_user_id="admin-id",
            actor_role="admin",
            expected_generation=4,
            idempotency_key="additive-import",
            runtime_service="runtime",
            approved_checkpoint_sha256="different-checkpoint",
            approved_database_sha256=current.package_sha256,
            approved_desired_sha256="unused",
        )
    except ThemeResearchDomainError as exc:
        assert exc.code == "THEME_RESEARCH_RESTORE_SNAPSHOT_MISMATCH"
    else:
        raise AssertionError("expected snapshot mismatch")
