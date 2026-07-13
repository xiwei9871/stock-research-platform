from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from stock_research.config import SETTINGS
from stock_research.dashboard.research_queue_health import load_research_queue_counts
from stock_research.research_case_seed import run_research_case_seed, run_research_case_seed_idempotency_audit
from stock_research.research_evidence_backfill import run_research_evidence_backfill
from stock_research.research_objects import apply_research_object_schema


def run_research_queue_refresh(
    *,
    trade_date: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
    skip_idempotency_audit: bool = False,
    output_dir: str | Path = "outputs/research/research_queue_refresh_v1",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    started_at = _now()
    run_id = f"research_queue_refresh:{uuid4().hex}"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    artifact_paths: dict[str, str] = {}
    limit_value = _clamp_limit(limit)

    schema_status = "skipped_dry_run"
    evidence_summary: dict[str, Any] = {}
    case_seed_summary: dict[str, Any] = {}
    audit_summary: dict[str, Any] = {"status": "skipped"}

    try:
        if not dry_run:
            apply_research_object_schema(service=service)
            schema_status = "applied"

        evidence_summary = run_research_evidence_backfill(
            trade_date=trade_date,
            source_type="all",
            dry_run=dry_run,
            limit=limit_value,
            output_dir=output_path,
            service=service,
        )
        _collect_artifact_paths(artifact_paths, "evidence_backfill", evidence_summary)

        case_seed_summary = run_research_case_seed(
            trade_date=trade_date,
            source_type="all",
            dry_run=dry_run,
            limit=limit_value,
            output_dir=output_path,
            service=service,
        )
        _collect_artifact_paths(artifact_paths, "case_seed", case_seed_summary)

        if dry_run:
            audit_summary = {"status": "skipped_dry_run"}
        elif skip_idempotency_audit:
            audit_summary = {"status": "skipped"}
        else:
            audit_summary = run_research_case_seed_idempotency_audit(
                trade_date=trade_date,
                source_type="all",
                limit=limit_value,
                output_dir=output_path,
                service=service,
            )
            _collect_artifact_paths(artifact_paths, "idempotency_audit", audit_summary)

        discovery_path = write_publication_entrypoint_discovery(output_path)
        if discovery_path:
            artifact_paths["publication_entrypoint_discovery"] = discovery_path

        counts = load_research_queue_counts(trade_date=trade_date, service=service)
        unmatched_digest = _int((case_seed_summary.get("skipped") or {}).get("unmatched_digest"))
        error_count = len(evidence_summary.get("errors") or []) + len(case_seed_summary.get("errors") or []) + len(
            audit_summary.get("second_run", {}).get("errors") or audit_summary.get("errors") or []
        )
        counts.update({"unmatched_digest": unmatched_digest, "errors": error_count})
        status = _refresh_status(counts=counts, dry_run=dry_run)
    except Exception as exc:  # pragma: no cover - defensive runner envelope.
        counts = {
            "cases": 0,
            "open_cases": 0,
            "claims": 0,
            "evidence_artifacts": 0,
            "evidence_links": 0,
            "evidence_gap_count": 0,
            "unmatched_digest": _int((case_seed_summary.get("skipped") or {}).get("unmatched_digest")),
            "errors": 1,
        }
        warnings.append(str(exc))
        status = "failed"

    finished_at = _now()
    manifest = {
        "trade_date": trade_date or "",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "dry_run": bool(dry_run),
        "limit": limit_value,
        "schema_status": schema_status,
        "evidence_backfill": evidence_summary,
        "case_seed": case_seed_summary,
        "idempotency_audit": audit_summary,
        "counts": counts,
        "warnings": warnings,
        "artifact_paths": artifact_paths,
        "status": status,
    }
    manifest_paths = write_research_queue_refresh_manifest(manifest, output_dir=output_path)
    manifest["artifact_paths"].update(manifest_paths)
    write_research_queue_refresh_manifest(manifest, output_dir=output_path)
    return manifest


def write_research_queue_refresh_manifest(manifest: dict[str, Any], *, output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "research_queue_refresh_manifest.json"
    markdown_path = output_path / "research_queue_refresh_summary.md"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_manifest_markdown(manifest), encoding="utf-8")
    return {"manifest_json": str(json_path), "manifest_markdown": str(markdown_path)}


def write_publication_entrypoint_discovery(output_dir: str | Path, repo_root: str | Path | None = None) -> str:
    root = Path(repo_root or Path.cwd())
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    discovery_path = output_path / "publication_entrypoint_discovery.md"
    matches = _publication_matches(root)
    lines = [
        "# Publication Entrypoint Discovery",
        "",
        "## Scope",
        "- Discovery only. This run does not change publication code and does not attach publication_snapshot.",
        "",
        "## Findings",
    ]
    if matches:
        for item in matches[:80]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- No publication-related source matches found by keyword scan.")
    lines.extend(
        [
            "",
            "## Current Classification",
            "- Dashboard read-only routes/components expose generated reports, readiness, and research queue state.",
            "- `dashboard/src/**` publication matches are display/readiness labels or metadata rendering; they are not release entrypoints.",
            "- `src/stock_research/p5/notifications.py` contains Feishu preview/send code and is a plausible downstream public-delivery candidate.",
            "- Strategy/generated-report publish runners are candidate release infrastructure, but this scan did not prove a single canonical public-release entrypoint.",
            "- `publication_snapshot` should not be force-attached in this PR.",
            "",
            "## Recommended Candidate",
            "- The best future attachment point is the single runner that performs the final public release/write after readiness checks, likely near P5 notification/public delivery rather than dashboard read APIs.",
            "- A publish precheck should include `/api/research/queue/health` and require `status=healthy` before research queue content is considered publishable.",
            "",
        ]
    )
    discovery_path.write_text("\n".join(lines), encoding="utf-8")
    return str(discovery_path)


def _publication_matches(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["rg", "-n", "-i", "publish|publication|release|generated report|feishu", "src", "dashboard/src"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _collect_artifact_paths(target: dict[str, str], prefix: str, summary: dict[str, Any]) -> None:
    for key in ("json_path", "markdown_path", "manifest_json", "manifest_markdown"):
        value = summary.get(key)
        if value:
            target[f"{prefix}_{key}"] = str(value)


def _refresh_status(*, counts: dict[str, Any], dry_run: bool) -> str:
    if _int(counts.get("errors")) > 0:
        return "failed"
    if dry_run:
        return "partial"
    if _int(counts.get("cases")) <= 0:
        return "empty"
    if (
        _int(counts.get("unmatched_digest")) > 0
        or _int(counts.get("evidence_gap_count")) > 0
        or _int(counts.get("claims")) <= 0
        or _int(counts.get("evidence_artifacts")) <= 0
        or _int(counts.get("evidence_links")) <= 0
    ):
        return "partial"
    return "success"


def _manifest_markdown(manifest: dict[str, Any]) -> str:
    counts = manifest.get("counts") or {}
    return "\n".join(
        [
            "# Research Queue Refresh",
            "",
            f"- trade_date: {manifest.get('trade_date') or ''}",
            f"- run_id: {manifest.get('run_id') or ''}",
            f"- status: {manifest.get('status') or ''}",
            f"- dry_run: {manifest.get('dry_run')}",
            f"- cases: {counts.get('cases', 0)}",
            f"- claims: {counts.get('claims', 0)}",
            f"- evidence_artifacts: {counts.get('evidence_artifacts', 0)}",
            f"- evidence_links: {counts.get('evidence_links', 0)}",
            f"- unmatched_digest: {counts.get('unmatched_digest', 0)}",
            f"- evidence_gap_count: {counts.get('evidence_gap_count', 0)}",
            f"- errors: {counts.get('errors', 0)}",
            "",
        ]
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp_limit(value: int) -> int:
    return max(1, min(1000, int(value or 100)))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
