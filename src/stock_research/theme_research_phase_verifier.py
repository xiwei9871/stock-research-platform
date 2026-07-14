from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from fastapi.testclient import TestClient

from stock_research.ai_power_source_pack import (
    _validate_claim_reviews,
    _validate_node_matrix,
    _validate_source_claim_references,
    load_ai_power_evidence_pack,
    summarize_ai_power_evidence_pack,
    validate_theme_evidence_sources,
)
from stock_research.config import SETTINGS
from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.daily_review_lite import build_daily_review_lite
from stock_research.dashboard.theme_research import list_theme_research_themes
from stock_research.dashboard.theme_research_context import (
    load_asset_theme_context,
)
from stock_research.dashboard.theme_research_db import load_db_context
from stock_research.dashboard.watchlist import load_watchlist_signals_for_dashboard
from stock_research.db import connect, fetch_all
from stock_research.decomposition_templates import (
    load_decomposition_template_library,
    summarize_decomposition_template_library,
)
from stock_research.theme_company_mapping import (
    load_theme_company_mapping_package,
    summarize_theme_company_mapping_package,
)
from stock_research.theme_decomposition import (
    load_theme_package,
    summarize_theme_package,
)
from stock_research.theme_research_db_schema import theme_research_schema_status
from stock_research.theme_research_import import normalize_artifact_package, semantic_diff
from stock_research.theme_research_ingestion import create_ingestion_run, load_run
from stock_research.theme_research_priority import (
    load_theme_research_priority_package,
    summarize_theme_research_priority_package,
)
from stock_research.theme_research_store import load_database_package
from stock_research.theme_tech_bottleneck_crosswalk import (
    load_theme_tech_bottleneck_crosswalk_package,
    summarize_theme_tech_bottleneck_crosswalk_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "research" / "theme_research_phase_verification"
PHASE_ORDER = ("1", "1.5", "2A", "2B", "3", "4", "5", "6", "7", "8", "9", "10")
WAVE_A_BATCH_MANIFEST = (
    "artifacts/theme_decomposition/batch_manifests/"
    "next_fifteen_industry_chain_themes_v1.json"
)
HUMANOID_THEME_ID = "humanoid_robotics_head_to_toe_v1"
HUMANOID_SOURCE_PACK_SPECS = {
    "humanoid_robotics_source_pack_v1.json": (
        "humanoid_robotics_source_pack_v1",
        "sources",
    ),
    "humanoid_robotics_claim_review_v1.json": (
        "humanoid_robotics_claim_review_v1",
        "claim_reviews",
    ),
    "humanoid_robotics_node_evidence_matrix_v1.json": (
        "humanoid_robotics_node_evidence_matrix_v1",
        "node_evidence_matrix",
    ),
}


def verify_theme_research_phases(
    *,
    migration_service: str | None = None,
    runtime_service: str | None = None,
    database_probe: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    probes: list[tuple[str, str, Callable[[], dict[str, Any]]]] = [
        ("1", "Read-only research baseline", _verify_phase_1),
        ("1.5", "Source, claim, and node review gates", _verify_phase_1_5),
        ("2A", "AI power public source pack", _verify_phase_2a),
        ("2B", "Humanoid robotics public source pack", _verify_phase_2b),
        ("3", "Decomposition method library", _verify_phase_3),
        ("4", "Theme node to company mapping", _verify_phase_4),
        ("5", "Tech bottleneck universe crosswalk", _verify_phase_5),
        ("6", "Research priority and review workflow", _verify_phase_6),
        ("7", "Read-only dashboard", _verify_phase_7),
        ("8", "Human-gated ingestion", _verify_phase_8),
    ]
    phases = [
        _run_probe(phase, title, probe)
        for phase, title, probe in probes
    ]
    if database_probe is not None:
        phases.append(_normalize_probe_result("9", "Database productionization", database_probe()))
    else:
        phases.append(
            _run_probe(
                "9",
                "Database productionization",
                lambda: _verify_phase_9(
                    migration_service=migration_service,
                    runtime_service=runtime_service,
                ),
            )
        )
    phases.append(
        _run_probe(
            "10",
            "Investment research workflow integration",
            lambda: _verify_phase_10(runtime_service=runtime_service),
        )
    )
    phases.sort(key=lambda row: PHASE_ORDER.index(row["phase"]))
    return build_verification_report(phases)


def build_verification_report(phases: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [str(row.get("status") or "failed") for row in phases]
    failed_count = statuses.count("failed") + statuses.count("not_run")
    declared_gap_count = statuses.count("declared_evidence_gap")
    if failed_count:
        overall_status = "failed"
    elif declared_gap_count:
        overall_status = "complete_with_declared_evidence_gap"
    else:
        overall_status = "complete"
    return {
        "schema_version": "theme_research_p1_p10_verification_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "phase_count": len(phases),
        "complete_phase_count": statuses.count("complete"),
        "declared_evidence_gap_phase_count": declared_gap_count,
        "failed_phase_count": failed_count,
        "phases": phases,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }


def write_verification_report(
    report: dict[str, Any],
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "theme_research_p1_p10_verification.json"
    markdown_path = root / "theme_research_p1_p10_verification.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_verification_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def render_verification_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Theme Research P1-P10 Verification",
        "",
        f"Overall status: `{report['overall_status']}`",
        "",
    ]
    for phase in report["phases"]:
        lines.extend(
            [
                f"## Phase {phase['phase']}: {phase['title']}",
                "",
                f"Status: `{phase['status']}`",
                "",
            ]
        )
        for requirement in phase.get("requirements", []):
            lines.append(
                f"- [{requirement['status']}] {requirement['requirement']}: "
                f"{requirement['evidence']}"
            )
        lines.append("")
    lines.extend(
        [
            "## Guardrails",
            "",
            "- research_only: true",
            "- used_for_signal: false",
            "- used_for_admission: false",
            "",
        ]
    )
    return "\n".join(lines)


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify-p1-p10")
    verify.add_argument("--migration-service", default=SETTINGS.theme_research_migration_service)
    verify.add_argument("--runtime-service", default=SETTINGS.theme_research_runtime_service)
    verify.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    if args.command != "verify-p1-p10":
        raise AssertionError(f"unhandled command: {args.command}")
    report = verify_theme_research_phases(
        migration_service=args.migration_service,
        runtime_service=args.runtime_service,
    )
    paths = write_verification_report(report, args.output_dir)
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "phase_count": report["phase_count"],
                **paths,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["overall_status"] != "failed" else 2


def _verify_phase_1() -> dict[str, Any]:
    package = load_theme_package()
    summary = summarize_theme_package(package)
    expected_wave_a_theme_ids = _load_wave_a_expected_theme_ids()
    actual_theme_ids = {row["theme_id"] for row in package["themes"]}
    missing_wave_a_theme_ids = sorted(expected_wave_a_theme_ids - actual_theme_ids)
    actual_counts = {
        "theme_count": len(package["themes"]),
        "node_count": len(package["nodes"]),
        "source_count": len(package["sources"]),
        "claim_count": len(package["claims"]),
    }
    roadmap = (REPOSITORY_ROOT / "docs" / "theme_driven_research_engine_roadmap.md").read_text(
        encoding="utf-8"
    )
    requirements = [
        _requirement(
            "canonical theme artifacts and nodes load",
            actual_counts["theme_count"] >= 2
            and actual_counts["node_count"] > 0
            and summary["theme_count"] == actual_counts["theme_count"]
            and summary["node_count"] == actual_counts["node_count"]
            and not missing_wave_a_theme_ids,
            (
                f"themes={summary['theme_count']}/{actual_counts['theme_count']}, "
                f"nodes={summary['node_count']}/{actual_counts['node_count']}, "
                f"missing_wave_a_themes={missing_wave_a_theme_ids}"
            ),
        ),
        _requirement(
            "source and claim summaries are populated and consistent",
            actual_counts["source_count"] > 0
            and actual_counts["claim_count"] > 0
            and summary["source_count"] == actual_counts["source_count"]
            and summary["claim_count"] == actual_counts["claim_count"],
            (
                f"sources={summary['source_count']}/{actual_counts['source_count']}, "
                f"claims={summary['claim_count']}/{actual_counts['claim_count']}"
            ),
        ),
        _requirement(
            "research boundaries remain documented",
            "does not copy short-video opinions" in roadmap
            and "does not" in roadmap
            and "buy/sell" in roadmap,
            "roadmap retains source-traceability and no-recommendation boundaries",
        ),
    ]
    return _phase_result("1", "Read-only research baseline", requirements)


def _verify_phase_1_5() -> dict[str, Any]:
    package = load_theme_package()
    source_by_id = {row["source_id"]: row for row in package["sources"]}
    invalid_s4 = [
        row["source_id"]
        for row in package["sources"]
        if row["reliability_level"] == "S4" and row["review_status"] == "accepted"
    ]
    invalid_claims = []
    for claim in package["claims"]:
        if claim["platform_use_status"] != "reviewed":
            continue
        source_ids = {claim["source_id"], *claim["supporting_source_ids"]}
        if not any(source_by_id[source_id]["review_status"] == "accepted" for source_id in source_ids):
            invalid_claims.append(claim["claim_id"])
    invalid_nodes = [
        row["node_id"]
        for row in package["nodes"]
        if row["node_review_status"] == "reviewed" and row["evidence_strength"] < 3
    ]
    requirements = [
        _requirement("S4 sources cannot be accepted", not invalid_s4, f"invalid={invalid_s4}"),
        _requirement(
            "reviewed claims have accepted evidence",
            not invalid_claims,
            f"invalid={invalid_claims}",
        ),
        _requirement(
            "reviewed nodes have evidence strength at least 3",
            not invalid_nodes,
            f"invalid={invalid_nodes}",
        ),
    ]
    return _phase_result("1.5", "Source, claim, and node review gates", requirements)


def _verify_phase_2a() -> dict[str, Any]:
    package = load_ai_power_evidence_pack()
    summary = summarize_ai_power_evidence_pack(package)
    requirements = [
        _requirement(
            "AI power source pack validates",
            summary["accepted_source_count"] >= 7,
            f"accepted_sources={summary['accepted_source_count']}",
        ),
        _requirement(
            "all canonical AI power nodes are covered",
            summary["node_count"] == 13,
            f"node_matrix_rows={summary['node_count']}",
        ),
        _requirement(
            "unresolved full-text targets remain explicit",
            summary["needs_full_text_source_count"] > 0,
            f"needs_full_text={summary['needs_full_text_source_count']}",
        ),
    ]
    return _phase_result("2A", "AI power public source pack", requirements)


def _verify_phase_2b() -> dict[str, Any]:
    source_pack_root = REPOSITORY_ROOT / "artifacts" / "theme_decomposition" / "source_packs"
    expected = [source_pack_root / filename for filename in HUMANOID_SOURCE_PACK_SPECS]
    present = [path.name for path in expected if path.exists()]
    theme_package = load_theme_package()
    robotics_theme = next(
        row
        for row in theme_package["themes"]
        if row["theme_id"] == HUMANOID_THEME_ID
    )
    declared_gap_is_valid = not present and robotics_theme["status"] == "draft"
    validation_errors: list[str] = []
    if len(present) == len(expected) and robotics_theme["status"] == "reviewed":
        try:
            _validate_humanoid_evidence_pack(source_pack_root, theme_package)
        except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            validation_errors.append(f"{type(exc).__name__}: {exc}")
    elif not declared_gap_is_valid:
        validation_errors.append(
            "source-pack presence and theme review status do not form an allowed state"
        )
    if (
        not validation_errors
        and len(present) == len(expected)
        and robotics_theme["status"] == "reviewed"
    ):
        status = "complete"
        requirement_status = "passed"
    elif declared_gap_is_valid:
        status = "declared_evidence_gap"
        requirement_status = "declared_gap"
    else:
        status = "failed"
        requirement_status = "failed"
    return {
        "phase": "2B",
        "title": "Humanoid robotics public source pack",
        "status": status,
        "requirements": [
            {
                "requirement": "source-pack files and theme review status form a coherent evidence state",
                "status": requirement_status,
                "evidence": (
                    f"present_source_pack_files={present}; "
                    f"validation_errors={validation_errors}; "
                    f"artifact_status={robotics_theme['status']}; "
                    "valid_states=complete_reviewed_or_declared_draft_gap"
                ),
            }
        ],
    }


def _verify_phase_3() -> dict[str, Any]:
    library = load_decomposition_template_library()
    summary = summarize_decomposition_template_library(library)
    families = set(summary["templates_by_family"])
    requirements = [
        _requirement(
            "three reusable template families validate",
            summary["template_count"] == 3
            and families == {"system_bottleneck", "head_to_toe", "manufacturing_process"},
            f"templates={summary['template_count']}, families={sorted(families)}",
        )
    ]
    return _phase_result("3", "Decomposition method library", requirements)


def _verify_phase_4() -> dict[str, Any]:
    package = load_theme_company_mapping_package()
    summary = summarize_theme_company_mapping_package(package)
    expected_wave_a_theme_ids = _load_wave_a_expected_theme_ids()
    mapping_count = len(package["company_mappings"])
    reviewed_mapping_count = sum(
        row["review_status"] == "reviewed"
        for row in package["company_mappings"]
    )
    missing_evidence = [
        row["mapping_id"]
        for row in package["company_mappings"]
        if row["review_status"] == "reviewed" and not row["evidence_ids"]
    ]
    reviewed_theme_ids = {
        row["theme_id"]
        for row in package["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    missing_wave_a_theme_ids = sorted(expected_wave_a_theme_ids - reviewed_theme_ids)
    requirements = [
        _requirement(
            "company mappings validate",
            mapping_count > 0 and summary["mapping_count"] == mapping_count,
            (
                f"mappings={summary['mapping_count']}/{mapping_count}, "
                f"companies={summary['company_count']}"
            ),
        ),
        _requirement(
            "reviewed mappings are evidence-backed",
            reviewed_mapping_count > 0
            and not missing_evidence
            and not missing_wave_a_theme_ids,
            (
                f"reviewed_mappings={reviewed_mapping_count}, "
                f"missing_evidence={missing_evidence}, "
                f"missing_wave_a_themes={missing_wave_a_theme_ids}"
            ),
        ),
    ]
    return _phase_result("4", "Theme node to company mapping", requirements)


def _verify_phase_5() -> dict[str, Any]:
    package = load_theme_tech_bottleneck_crosswalk_package()
    summary = summarize_theme_tech_bottleneck_crosswalk_package(package)
    requirements = [
        _requirement(
            "all Phase 4 mappings are accounted for",
            summary["mapping_coverage_rate"] == 1.0,
            f"coverage={summary['accounted_mapping_count']}/{summary['p4_mapping_count']}",
        ),
        _requirement(
            "existing tech-bottleneck universe remains the crosswalk source",
            summary["universe_count"] > 0,
            f"universe_rows={summary['universe_count']}",
        ),
    ]
    return _phase_result("5", "Tech bottleneck universe crosswalk", requirements)


def _verify_phase_6() -> dict[str, Any]:
    package = load_theme_research_priority_package()
    summary = summarize_theme_research_priority_package(package)
    expected_wave_a_theme_ids = _load_wave_a_expected_theme_ids()
    node_priority_count = len(package["node_priorities"])
    company_priority_count = len(package["company_priorities"])
    node_priority_theme_ids = {row["theme_id"] for row in package["node_priorities"]}
    company_priority_theme_ids = {
        row["theme_id"] for row in package["company_priorities"]
    }
    mapped_wave_a_theme_ids = {
        row["theme_id"]
        for row in package["mapping_package"]["company_mappings"]
        if row["theme_id"] in expected_wave_a_theme_ids
        and row["review_status"] == "reviewed"
    }
    missing_wave_a_node_priorities = sorted(
        expected_wave_a_theme_ids - node_priority_theme_ids
    )
    missing_wave_a_company_priorities = sorted(
        mapped_wave_a_theme_ids - company_priority_theme_ids
    )
    requirements = [
        _requirement(
            "node and company priorities are generated",
            node_priority_count > 0
            and company_priority_count > 0
            and summary["node_priority_count"] == node_priority_count
            and summary["company_priority_count"] == company_priority_count
            and not missing_wave_a_node_priorities
            and not missing_wave_a_company_priorities,
            (
                f"node_priorities={summary['node_priority_count']}/{node_priority_count}, "
                f"company_priorities={summary['company_priority_count']}/{company_priority_count}, "
                f"missing_wave_a_node_priorities={missing_wave_a_node_priorities}, "
                f"missing_wave_a_company_priorities={missing_wave_a_company_priorities}"
            ),
        ),
        _requirement(
            "human review and evidence-gap queues are populated",
            summary["human_review_queue_count"] > 0
            and summary["evidence_gap_priority_count"] > 0,
            (
                f"review_queue={summary['human_review_queue_count']}, "
                f"evidence_gaps={summary['evidence_gap_priority_count']}"
            ),
        ),
    ]
    return _phase_result("6", "Research priority and review workflow", requirements)


def _verify_phase_7() -> dict[str, Any]:
    payload = list_theme_research_themes(read_source="artifact")
    expected_wave_a_theme_ids = _load_wave_a_expected_theme_ids()
    canonical_theme_count = len(load_theme_package()["themes"])
    dashboard_theme_ids = {row["theme_id"] for row in payload["items"]}
    missing_wave_a_theme_ids = sorted(expected_wave_a_theme_ids - dashboard_theme_ids)
    guarded = all(
        row["research_only"] is True
        and row["used_for_signal"] is False
        and row["used_for_admission"] is False
        for row in payload["items"]
    )
    requirements = [
        _requirement(
            "read-only dashboard exposes the canonical themes",
            canonical_theme_count > 0
            and payload["total"] == canonical_theme_count
            and len(payload["items"]) == payload["total"]
            and not missing_wave_a_theme_ids,
            (
                f"dashboard_theme_count={payload['total']}, "
                f"canonical_theme_count={canonical_theme_count}, "
                f"missing_wave_a_themes={missing_wave_a_theme_ids}"
            ),
        ),
        _requirement(
            "dashboard guardrails are explicit",
            guarded,
            "all theme index rows are research-only and disabled for signal/admission",
        ),
    ]
    return _phase_result("7", "Read-only dashboard", requirements)


def _verify_phase_8() -> dict[str, Any]:
    sample = (
        REPOSITORY_ROOT
        / "artifacts"
        / "theme_decomposition"
        / "ingestion_samples"
        / "ai_power_video_claim_lead_v1.json"
    )
    with tempfile.TemporaryDirectory(prefix="theme-research-verifier-") as temp_dir:
        created = create_ingestion_run(
            sample,
            input_type="manual_claim_json",
            theme_hint="ai_power_value_capture_v1",
            runs_dir=temp_dir,
        )
        run = load_run(created["run_dir"])
    queue_pending = all(
        row["status"] == "pending_human_review"
        for row in run["review_queue"]
    )
    preview_empty = not run["promotion_preview"]["promotable_sources"] and not run[
        "promotion_preview"
    ]["promotable_claims"]
    requirements = [
        _requirement(
            "ingestion stages candidates for human review",
            run["manifest"]["status"] == "pending_human_review" and queue_pending,
            (
                f"manifest_status={run['manifest']['status']}, "
                f"queue_items={len(run['review_queue'])}"
            ),
        ),
        _requirement(
            "ingestion does not auto-promote",
            preview_empty,
            "promotion preview is empty before explicit review decisions",
        ),
    ]
    return _phase_result("8", "Human-gated ingestion", requirements)


def _verify_phase_9(
    *,
    migration_service: str | None,
    runtime_service: str | None,
) -> dict[str, Any]:
    migration = migration_service or SETTINGS.theme_research_migration_service
    runtime = runtime_service or SETTINGS.theme_research_runtime_service
    schema = theme_research_schema_status(service=migration)
    artifact_package = normalize_artifact_package()
    database_package = load_database_package(service=runtime)
    diff = semantic_diff(artifact_package, database_package)
    with connect(runtime) as conn:
        privilege = fetch_all(
            conn,
            """
            SELECT current_user AS user_name,
                   has_table_privilege(current_user, 'research.theme_research_theme', 'SELECT') AS can_select,
                   has_table_privilege(current_user, 'research.theme_research_theme', 'INSERT') AS can_insert,
                   has_table_privilege(current_user, 'research.theme_research_theme', 'UPDATE') AS can_update,
                   has_table_privilege(current_user, 'research.theme_research_theme', 'DELETE') AS can_delete,
                   has_table_privilege(current_user, 'research.theme_research_theme', 'TRUNCATE') AS can_truncate,
                   has_schema_privilege(current_user, 'research', 'CREATE') AS can_create_schema_objects,
                   has_table_privilege(current_user, 'research.theme_research_review_event', 'UPDATE') AS history_update,
                   has_table_privilege(current_user, 'research.theme_research_review_event', 'TRUNCATE') AS history_truncate,
                   has_table_privilege(current_user, 'research.theme_research_snapshot', 'UPDATE') AS snapshot_update,
                   has_table_privilege(current_user, 'research.theme_research_snapshot', 'TRUNCATE') AS snapshot_truncate
            """,
            [],
        )[0]
        history = fetch_all(
            conn,
            """
            SELECT
                count(*) FILTER (WHERE snapshot_type = 'rollback') AS rollback_snapshot_count,
                count(*) AS snapshot_count
            FROM research.theme_research_snapshot
            """,
            [],
        )[0]
    runtime_constrained = _runtime_privileges_are_constrained(privilege)
    requirements = [
        _requirement(
            "database schema is current",
            schema["status"] == "current" and schema["ddl_matches"] is True,
            f"status={schema['status']}, schema_version={schema['schema_version']}",
        ),
        _requirement(
            "database package matches authoritative artifacts",
            diff["has_changes"] is False
            and artifact_package.package_sha256 == database_package.package_sha256,
            (
                f"artifact_sha={artifact_package.package_sha256}, "
                f"database_sha={database_package.package_sha256}"
            ),
        ),
        _requirement(
            "runtime role permits controlled reviews but protects canonical deletion and history",
            runtime_constrained,
            (
                f"runtime_user={privilege['user_name']}, select={privilege['can_select']}, "
                f"insert={privilege['can_insert']}, update={privilege['can_update']}, "
                f"delete={privilege['can_delete']}, truncate={privilege['can_truncate']}"
            ),
        ),
        _requirement(
            "versioned snapshots and rollback evidence exist",
            int(history["snapshot_count"] or 0) > 0
            and int(history["rollback_snapshot_count"] or 0) > 0,
            (
                f"snapshots={int(history['snapshot_count'] or 0)}, "
                f"rollback_snapshots={int(history['rollback_snapshot_count'] or 0)}"
            ),
        ),
    ]
    return _phase_result("9", "Database productionization", requirements)


def _verify_phase_10(*, runtime_service: str | None = None) -> dict[str, Any]:
    from stock_research.dashboard.app import create_app

    service = runtime_service or SETTINGS.theme_research_runtime_service
    context = load_db_context(service=service)
    mapped_codes = sorted(
        {row["company_code"] for row in context["mapping_package"]["company_mappings"]}
    )
    asset_contexts = [
        load_asset_theme_context(code, service=service) for code in mapped_codes
    ]
    eligible = [row for row in asset_contexts if row["status"] == "reviewed_context_available"]
    reviewed_theme_ids = {
        row["theme_id"]
        for row in context["theme_package"]["themes"]
        if row["status"] in {"reviewed", "published"}
    }
    guarded = all(
        row["research_only"] is True
        and row["used_for_signal"] is False
        and row["used_for_admission"] is False
        for row in asset_contexts
    )
    eligible_theme_ids = {
        theme["theme_id"] for row in eligible for theme in row["themes"]
    }
    robotics_theme_id = "humanoid_robotics_head_to_toe_v1"
    robotics_excluded = robotics_theme_id not in eligible_theme_ids
    daily_payload = build_daily_review_lite("2026-07-11")
    daily_section = next(
        row for row in daily_payload["sections"] if row["key"] == "theme_research"
    )
    digest = daily_payload["theme_research"]
    raw_watchlist_rows = load_watchlist_signals_for_dashboard(
        "default",
        "2026-07-10",
        include_theme_research=False,
    )
    enriched_rows = load_watchlist_signals_for_dashboard(
        "default",
        "2026-07-10",
    )
    signal_fields_unchanged = all(
        all(enriched.get(key) == original.get(key) for key in original)
        for original, enriched in zip(raw_watchlist_rows, enriched_rows, strict=True)
    )
    profile = build_asset_profile(
        eligible[0]["company_code"],
        "2026-07-10",
        "2026-07-01",
        "2026-07-10",
    )
    auth_override = os.environ.get("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED")
    os.environ["STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED"] = "false"
    try:
        client = TestClient(create_app())
        asset_response = client.get(
            f"/api/assets/{eligible[0]['company_code']}/theme-research-context"
        )
        updates_response = client.get(
            "/api/research/theme-decomposition/updates",
            params={"since": "2026-07-11", "limit": 20},
        )
    finally:
        if auth_override is None:
            os.environ.pop("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", None)
        else:
            os.environ["STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED"] = auth_override
    requirements = [
        _requirement(
            "reviewed company context is available and fail-closed",
            bool(eligible)
            and guarded
            and eligible_theme_ids <= reviewed_theme_ids
            and robotics_excluded,
            (
                f"eligible_companies={len(eligible)}, "
                f"reviewed_themes={sorted(reviewed_theme_ids)}, "
                f"robotics_excluded={robotics_excluded}"
            ),
        ),
        _requirement(
            "Daily Review consumes the shared digest",
            daily_section["status"] == "ready"
            and digest["mapped_company_count"] == len(eligible),
            (
                f"daily_section={daily_section['status']}, "
                f"mapped_companies={digest['mapped_company_count']}"
            ),
        ),
        _requirement(
            "Watchlist and Asset Profile execute their real loaders",
            signal_fields_unchanged
            and len(raw_watchlist_rows) == len(enriched_rows)
            and all("theme_research_context" in row for row in enriched_rows)
            and profile["theme_research_context"]["status"]
            == "reviewed_context_available",
            (
                f"watchlist_rows={len(enriched_rows)}, "
                f"signal_fields_unchanged={signal_fields_unchanged}, "
                f"profile_status={profile['theme_research_context']['status']}"
            ),
        ),
        _requirement(
            "HTTP read APIs execute the DB-backed context service",
            asset_response.status_code == 200
            and asset_response.json()["status"] == "reviewed_context_available"
            and asset_response.json()["research_only"] is True
            and updates_response.status_code == 200
            and updates_response.json()["research_only"] is True,
            (
                f"asset_http={asset_response.status_code}, "
                f"updates_http={updates_response.status_code}, "
                f"updates={updates_response.json().get('total')}"
            ),
        ),
    ]
    return _phase_result("10", "Investment research workflow integration", requirements)


def _run_probe(
    phase: str,
    title: str,
    probe: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        return _normalize_probe_result(phase, title, probe())
    except Exception as exc:
        return {
            "phase": phase,
            "title": title,
            "status": "failed",
            "requirements": [
                {
                    "requirement": "phase verifier executes without error",
                    "status": "failed",
                    "evidence": f"{type(exc).__name__}: {exc}",
                }
            ],
        }


def _normalize_probe_result(
    phase: str,
    title: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {"phase": phase, "title": title, **result}


def _phase_result(
    phase: str,
    title: str,
    requirements: list[dict[str, str]],
) -> dict[str, Any]:
    status = "complete" if all(row["status"] == "passed" for row in requirements) else "failed"
    return {
        "phase": phase,
        "title": title,
        "status": status,
        "requirements": requirements,
    }


def _runtime_privileges_are_constrained(privilege: dict[str, Any]) -> bool:
    return (
        bool(privilege.get("can_select"))
        and bool(privilege.get("can_insert"))
        and bool(privilege.get("can_update"))
        and not any(
            bool(privilege.get(key))
            for key in (
                "can_delete",
                "can_truncate",
                "can_create_schema_objects",
                "history_update",
                "history_truncate",
                "snapshot_update",
                "snapshot_truncate",
            )
        )
    )


def _load_wave_a_expected_theme_ids() -> set[str]:
    manifest_path = REPOSITORY_ROOT / WAVE_A_BATCH_MANIFEST
    manifest = _load_json_object(manifest_path)
    wave_a = manifest.get("waves", {}).get("wave_a")
    themes = manifest.get("themes")
    if not isinstance(wave_a, list) or not isinstance(themes, dict):
        raise ValueError(f"invalid Wave A batch manifest: {manifest_path}")
    expected_theme_ids = {
        themes[chain_id]["theme_id"]
        for chain_id in wave_a
        if isinstance(themes.get(chain_id), dict)
        and isinstance(themes[chain_id].get("theme_id"), str)
    }
    if len(wave_a) != 5 or len(expected_theme_ids) != 5:
        raise ValueError(
            "Wave A batch manifest must resolve exactly five unique theme_ids; "
            f"chains={wave_a}, theme_ids={sorted(expected_theme_ids)}"
        )
    return expected_theme_ids


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} root must be a JSON object")
    return payload


def _validate_humanoid_evidence_pack(
    source_pack_root: Path,
    theme_package: dict[str, Any],
) -> None:
    payloads: dict[str, dict[str, Any]] = {}
    for filename, (artifact_version, list_field) in HUMANOID_SOURCE_PACK_SPECS.items():
        payload = _load_json_object(source_pack_root / filename)
        if payload.get("artifact_version") != artifact_version:
            raise ValueError(
                f"{filename}.artifact_version must be {artifact_version}"
            )
        if payload.get("theme_id") != HUMANOID_THEME_ID:
            raise ValueError(
                f"{filename}.theme_id must be {HUMANOID_THEME_ID}"
            )
        rows = payload.get(list_field)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{filename}.{list_field} must be a non-empty list")
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError(f"{filename}.{list_field} rows must be JSON objects")
        payloads[filename] = payload

    canonical_node_ids = {
        row["node_id"]
        for row in theme_package["nodes"]
        if row["theme_id"] == HUMANOID_THEME_ID
    }
    canonical_claims = {
        row["claim_id"]: row
        for row in theme_package["claims"]
        if row["theme_id"] == HUMANOID_THEME_ID
    }
    if not canonical_node_ids or not canonical_claims:
        raise ValueError("canonical humanoid theme nodes and claims must be populated")

    sources = payloads["humanoid_robotics_source_pack_v1.json"]["sources"]
    claim_reviews = payloads["humanoid_robotics_claim_review_v1.json"][
        "claim_reviews"
    ]
    matrix = payloads["humanoid_robotics_node_evidence_matrix_v1.json"][
        "node_evidence_matrix"
    ]
    source_by_id = validate_theme_evidence_sources(sources, canonical_node_ids)
    accepted_source_ids = {
        source_id
        for source_id, row in source_by_id.items()
        if row["review_status"] == "accepted"
    }
    if len(accepted_source_ids) < 10:
        raise ValueError(
            "humanoid source pack requires at least 10 accepted sources; "
            f"accepted={len(accepted_source_ids)}"
        )

    claim_by_id = _validate_claim_reviews(
        claim_reviews,
        source_by_id=source_by_id,
        canonical_node_ids=canonical_node_ids,
    )
    reviewed_claim_ids = {
        claim_id
        for claim_id, row in claim_by_id.items()
        if row["review_decision"] == "reviewed"
    }
    canonical_reviewed_claim_ids = {
        claim_id
        for claim_id, row in canonical_claims.items()
        if row["platform_use_status"] == "reviewed"
    }
    unknown_claim_ids = set(claim_by_id) - set(canonical_claims)
    missing_reviewed_claim_ids = canonical_reviewed_claim_ids - reviewed_claim_ids
    if len(reviewed_claim_ids) < 10 or unknown_claim_ids or missing_reviewed_claim_ids:
        raise ValueError(
            "humanoid claim reviews must cover canonical reviewed claims; "
            f"reviewed={len(reviewed_claim_ids)}, "
            f"unknown={sorted(unknown_claim_ids)}, "
            f"missing={sorted(missing_reviewed_claim_ids)}"
        )
    _validate_source_claim_references(sources, claim_by_id)
    _validate_node_matrix(
        matrix,
        source_by_id=source_by_id,
        claim_by_id=claim_by_id,
        canonical_node_ids=canonical_node_ids,
    )
    rows_without_evidence_or_gap = []
    for row in matrix:
        supported_claims = [claim_by_id[claim_id] for claim_id in row["supported_claim_ids"]]
        has_technical_route = any(
            claim["claim_type"] == "tech_route" for claim in supported_claims
        )
        has_explicit_gap = row["evidence_gap_status"] == "evidence_gap"
        if not row["accepted_source_ids"] and not has_explicit_gap and not has_technical_route:
            rows_without_evidence_or_gap.append(row["node_id"])
    if rows_without_evidence_or_gap:
        raise ValueError(
            "node matrix rows require accepted evidence or explicit gap/technical_route; "
            f"invalid={sorted(rows_without_evidence_or_gap)}"
        )


def _requirement(requirement: str, passed: bool, evidence: str) -> dict[str, str]:
    return {
        "requirement": requirement,
        "status": "passed" if passed else "failed",
        "evidence": evidence,
    }


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
