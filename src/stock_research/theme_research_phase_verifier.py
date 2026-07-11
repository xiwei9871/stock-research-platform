from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import tempfile
from typing import Any, Callable

from stock_research.ai_power_source_pack import (
    load_ai_power_evidence_pack,
    summarize_ai_power_evidence_pack,
)
from stock_research.config import SETTINGS
from stock_research.dashboard.daily_review_lite import _sections
from stock_research.dashboard.theme_research import list_theme_research_themes
from stock_research.dashboard.theme_research_context import (
    build_asset_theme_context,
    build_daily_theme_research_digest,
)
from stock_research.dashboard import asset_profile, watchlist
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
        _run_probe("10", "Investment research workflow integration", _verify_phase_10)
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
    roadmap = (REPOSITORY_ROOT / "docs" / "theme_driven_research_engine_roadmap.md").read_text(
        encoding="utf-8"
    )
    requirements = [
        _requirement(
            "two baseline theme artifacts load",
            summary["theme_count"] == 2 and summary["node_count"] == 34,
            f"themes={summary['theme_count']}, nodes={summary['node_count']}",
        ),
        _requirement(
            "source and claim summaries are populated",
            summary["source_count"] > 0 and summary["claim_count"] > 0,
            f"sources={summary['source_count']}, claims={summary['claim_count']}",
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
    expected = [
        source_pack_root / "humanoid_robotics_source_pack_v1.json",
        source_pack_root / "humanoid_robotics_claim_review_v1.json",
        source_pack_root / "humanoid_robotics_node_evidence_matrix_v1.json",
    ]
    present = [path.name for path in expected if path.exists()]
    return {
        "phase": "2B",
        "title": "Humanoid robotics public source pack",
        "status": "declared_evidence_gap",
        "requirements": [
            {
                "requirement": "unfinished evidence track is explicit and excluded from reviewed workflows",
                "status": "declared_gap",
                "evidence": (
                    f"present_source_pack_files={present}; expected files remain an explicit Phase 2B task"
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
    missing_evidence = [
        row["mapping_id"]
        for row in package["company_mappings"]
        if row["review_status"] == "reviewed" and not row["evidence_ids"]
    ]
    requirements = [
        _requirement(
            "company mappings validate",
            summary["mapping_count"] == 4,
            f"mappings={summary['mapping_count']}, companies={summary['company_count']}",
        ),
        _requirement(
            "reviewed mappings are evidence-backed",
            not missing_evidence,
            f"missing_evidence={missing_evidence}",
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
    requirements = [
        _requirement(
            "node and company priorities are generated",
            summary["node_priority_count"] == 34 and summary["company_priority_count"] == 4,
            (
                f"node_priorities={summary['node_priority_count']}, "
                f"company_priorities={summary['company_priority_count']}"
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
    guarded = all(
        row["research_only"] is True
        and row["used_for_signal"] is False
        and row["used_for_admission"] is False
        for row in payload["items"]
    )
    requirements = [
        _requirement(
            "read-only dashboard exposes both themes",
            payload["total"] == 2,
            f"dashboard_theme_count={payload['total']}",
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
                   has_table_privilege(current_user, 'research.theme_research_theme', 'TRUNCATE') AS can_truncate
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
    runtime_read_only = bool(privilege["can_select"]) and not any(
        bool(privilege[key])
        for key in ("can_insert", "can_update", "can_delete", "can_truncate")
    )
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
            "runtime role is read-only",
            runtime_read_only,
            f"runtime_user={privilege['user_name']}, select={privilege['can_select']}",
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


def _verify_phase_10() -> dict[str, Any]:
    context = load_theme_research_priority_package()
    mapped_codes = sorted(
        {row["company_code"] for row in context["mapping_package"]["company_mappings"]}
    )
    asset_contexts = [build_asset_theme_context(code, context) for code in mapped_codes]
    eligible = [row for row in asset_contexts if row["status"] == "reviewed_context_available"]
    guarded = all(
        row["research_only"] is True
        and row["used_for_signal"] is False
        and row["used_for_admission"] is False
        for row in asset_contexts
    )
    digest = build_daily_theme_research_digest(
        "2026-07-11",
        context=context,
        updates={"total": 0, "items": []},
    )
    daily_section = next(
        row
        for row in _sections(
            selected_trade_date="2026-07-11",
            summary={},
            market={},
            queue={},
            artifacts=[],
            run={},
            theme_research=digest,
        )
        if row["key"] == "theme_research"
    )
    backend_sources = "\n".join(
        [inspect.getsource(watchlist), inspect.getsource(asset_profile)]
    )
    frontend_files = [
        REPOSITORY_ROOT / "dashboard" / "src" / "components" / "DailyReviewLiteWorkspace.tsx",
        REPOSITORY_ROOT / "dashboard" / "src" / "components" / "WatchlistWorkspace.tsx",
        REPOSITORY_ROOT
        / "dashboard"
        / "src"
        / "components"
        / "stock-workspace"
        / "ThemeResearchContextSection.tsx",
        REPOSITORY_ROOT / "dashboard" / "src" / "components" / "StockWorkspace.tsx",
    ]
    frontend_text = "\n".join(path.read_text(encoding="utf-8") for path in frontend_files)
    requirements = [
        _requirement(
            "reviewed company context is available and fail-closed",
            len(eligible) == 2 and guarded,
            f"eligible_companies={len(eligible)}, mapped_candidates={len(asset_contexts)}",
        ),
        _requirement(
            "Daily Review consumes the shared digest",
            daily_section["status"] == "ready" and digest["mapped_company_count"] == 2,
            (
                f"daily_section={daily_section['status']}, "
                f"mapped_companies={digest['mapped_company_count']}"
            ),
        ),
        _requirement(
            "Watchlist and asset profile consume one context service",
            "enrich_watchlist_rows" in backend_sources
            and "load_asset_theme_context_for_workflow" in backend_sources,
            "watchlist enrichment and asset profile use theme_research_context",
        ),
        _requirement(
            "all three dashboard workflows render research-only context",
            "ThemeResearchContextSection" in frontend_text
            and "theme_research" in frontend_text
            and "不参与信号或准入" in frontend_text,
            "Daily Review, Watchlist, and Stock Workspace frontend consumers are present",
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
