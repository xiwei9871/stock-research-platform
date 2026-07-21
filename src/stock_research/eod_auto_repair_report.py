from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable

from stock_research.eod_auto_repair_models import RepairRunSummary, RepairStatus


JsonObject = dict[str, Any]


def summary_json_bytes(summary: RepairRunSummary) -> bytes:
    payload = json.dumps(
        summary.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )
    return (payload + "\n").encode("utf-8")


def _browser_action(payload: JsonObject) -> JsonObject:
    browser = payload.get("browser_acceptance")
    if not isinstance(browser, dict):
        return {}
    action = browser.get("action")
    return action if isinstance(action, dict) else {}


def _browser_evidence(payload: JsonObject) -> JsonObject:
    validation = _browser_action(payload).get("validation_result")
    if not isinstance(validation, dict):
        return {}
    evidence = validation.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def _safe_relative_evidence_paths(summary: RepairRunSummary, output_dir: str | Path) -> list[str]:
    output = Path(output_dir).resolve(strict=False)
    payload = summary.to_dict()
    action = _browser_action(payload)
    evidence = _browser_evidence(payload)
    candidates: list[object] = []
    for value in (action.get("artifact_paths"), evidence.get("report_paths")):
        if isinstance(value, list):
            candidates.extend(value)

    links: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        raw = Path(candidate)
        path = raw if raw.is_absolute() else output / raw
        try:
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(output)
        except (FileNotFoundError, OSError, RuntimeError, ValueError):
            continue
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != output.parent):
            continue
        if not resolved.is_file():
            continue
        links.add(relative.as_posix())
    return sorted(links)


def _report_context(summary: RepairRunSummary, output_dir: str | Path) -> JsonObject:
    payload = summary.to_dict()
    action = _browser_action(payload)
    evidence = _browser_evidence(payload)
    parsed = evidence.get("parsed_result")
    parsed = parsed if isinstance(parsed, dict) else {}
    metrics = action.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    publications = evidence.get("candidate_publications")
    publications = publications if isinstance(publications, list) else []
    attempts = parsed.get("attempts")
    attempts = attempts if isinstance(attempts, list) else []
    strategy_run_id = metrics.get("run_id") or parsed.get("run_id") or "n/a"
    browser_status = action.get("status") or parsed.get("status") or "not-run"
    return {
        "payload": payload,
        "action": action,
        "eod_run_id": summary.run_id or "n/a",
        "strategy_run_id": str(strategy_run_id),
        "browser_status": str(browser_status),
        "publications": [item for item in publications if isinstance(item, dict)],
        "attempts": [item for item in attempts if isinstance(item, dict)],
        "links": _safe_relative_evidence_paths(summary, output_dir),
    }


def _banner(summary: RepairRunSummary) -> str:
    if summary.final_status == RepairStatus.SUCCESS:
        return "official"
    if summary.final_status == RepairStatus.DEGRADED:
        return "degraded"
    return "blocked"


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def render_markdown_report(summary: RepairRunSummary, output_dir: str | Path) -> str:
    context = _report_context(summary, output_dir)
    action = context["action"]
    lines = [
        f"# EOD Auto Repair Report {summary.trade_date}",
        "",
        f"- EOD run ID: {context['eod_run_id']}",
        f"- Strategy cohort run ID: {context['strategy_run_id']}",
        "- Report path: run_report.md",
        f"- Trade date: {summary.trade_date}",
        f"- Mode: {summary.mode}",
        f"- Initial status: {summary.checks_before[0].status.value if summary.checks_before else 'unknown'}",
        f"- Final status: {summary.final_status.value}",
        f"- Publication decision: {_banner(summary)}",
        f"- Loop stop reason: {summary.loop_stop_reason or 'n/a'}",
        f"- Dry run: {summary.dry_run}",
        f"- Remaining blockers: {', '.join(summary.remaining_blockers) if summary.remaining_blockers else 'none'}",
        f"- Remaining non-blockers: {', '.join(summary.remaining_non_blockers) if summary.remaining_non_blockers else 'none'}",
        "",
        "## Stages",
    ]
    if summary.stages:
        for stage in summary.stages:
            blockers = ", ".join(stage.remaining_blockers) if stage.remaining_blockers else "none"
            lines.append(f"- {stage.name}: blockers={blockers}")
            for stage_action in stage.actions:
                lines.append(f"  - action {stage_action.name}: {stage_action.status.value} {stage_action.message}")
    else:
        lines.append("- none")

    lines.extend(["", "## Data and check results"])
    checks = [*summary.checks_before, *summary.checks_after]
    if checks:
        for check in checks:
            lines.append(
                f"- {check.name}: {check.status.value} blocker={str(check.blocker).lower()} "
                f"metrics={_json_text(check.metrics)} {check.message}".rstrip()
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Strategy publications"])
    if context["publications"]:
        for publication in context["publications"]:
            lines.append(
                "- "
                f"strategy={publication.get('strategyId', 'n/a')} "
                f"publish_id={publication.get('publishId', 'n/a')} "
                f"contract_id={publication.get('contractId', 'n/a')} "
                f"trade_date={publication.get('tradeDate', 'n/a')}"
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Browser acceptance",
            f"- Status: {context['browser_status']}",
            f"- Repair action: {action.get('name') or 'none'} — {action.get('message') or 'none'}",
        ]
    )
    attempts = context["attempts"]
    if attempts:
        for attempt in attempts:
            number = attempt.get("attempt_number", "?")
            lines.append(
                f"- Attempt {number}: {attempt.get('status', 'unknown')} "
                f"{attempt.get('message', '')}".rstrip()
            )
        last = attempts[-1]
        lines.append(
            f"- Rerun result: {last.get('status', 'unknown')} {last.get('message', '')}".rstrip()
        )
    else:
        lines.append("- Rerun result: not run")

    lines.extend(["", "## Evidence links"])
    if context["links"]:
        lines.extend(f"- [{path}]({path})" for path in context["links"])
    else:
        lines.append("- none")

    if summary.loop_cycles:
        lines.extend(["", "## Loop Cycles"])
        for cycle in summary.loop_cycles:
            blockers = ", ".join(cycle.remaining_blockers) if cycle.remaining_blockers else "none"
            lines.append(
                f"- Cycle {cycle.cycle_number}: actions={len(cycle.actions)} blockers={blockers} "
                f"stop={cycle.stop_reason or 'continue'}"
            )

    lines.extend(["", "## Actions"])
    if summary.actions:
        for repair_action in summary.actions:
            lines.append(
                f"- {repair_action.name}: {repair_action.status.value} exit_code={repair_action.exit_code} "
                f"started={repair_action.started_at} ended={repair_action.ended_at} "
                f"metrics={_json_text(repair_action.metrics)} "
                f"validation={_json_text(repair_action.validation_result)}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Next actions"])
    lines.extend(f"- {item}" for item in summary.next_actions or ["none"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in summary.warnings or ["none"])
    lines.extend(["", "## Infrastructure issues"])
    lines.extend(f"- {item}" for item in summary.infrastructure_issues or ["none"])
    lines.extend(["", "## Final decision"])
    if not summary.remaining_blockers and summary.final_status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}:
        lines.append(
            "System is usable for dashboard, watchlist, strategy publish, review queue, "
            "and market monitor surfaces. No blocking EOD issue remains. Remaining issues "
            "are degraded-only and should be handled by separate data gap or report generation loops."
        )
    else:
        lines.append("Blocking EOD issues remain; review failed actions and external data availability.")
    if summary.recommended_followups:
        lines.extend(["", "## Recommended follow-ups"])
        lines.extend(f"- {item}" for item in summary.recommended_followups)
    return "\n".join(lines) + "\n"


def render_html_report(summary: RepairRunSummary, output_dir: str | Path) -> str:
    context = _report_context(summary, output_dir)
    action = context["action"]

    def text(value: object) -> str:
        return escape(str(value), quote=True)

    checks = [*summary.checks_before, *summary.checks_after]
    check_items = "".join(
        f"<li><strong>{text(check.name)}</strong>: {text(check.status.value)} — {text(check.message)}</li>"
        for check in checks
    ) or "<li>none</li>"
    publication_items = "".join(
        "<li>"
        f"strategy={text(item.get('strategyId', 'n/a'))}; "
        f"publish_id={text(item.get('publishId', 'n/a'))}; "
        f"contract_id={text(item.get('contractId', 'n/a'))}; "
        f"trade_date={text(item.get('tradeDate', 'n/a'))}"
        "</li>"
        for item in context["publications"]
    ) or "<li>none</li>"
    attempt_items = "".join(
        f"<li>Attempt {text(item.get('attempt_number', '?'))}: "
        f"{text(item.get('status', 'unknown'))} — {text(item.get('message', ''))}</li>"
        for item in context["attempts"]
    ) or "<li>not run</li>"
    rerun = context["attempts"][-1] if context["attempts"] else {}
    rerun_text = (
        f"{rerun.get('status', 'unknown')} — {rerun.get('message', '')}".rstrip(" —")
        if rerun
        else "not run"
    )
    link_items = "".join(
        f'<li><a href="{text(path)}">{text(path)}</a></li>' for path in context["links"]
    ) or "<li>none</li>"
    issue_items = "".join(f"<li>{text(issue)}</li>" for issue in summary.infrastructure_issues) or "<li>none</li>"
    blocker_text = ", ".join(summary.remaining_blockers) if summary.remaining_blockers else "none"
    decision = (
        "Official EOD evidence is publishable."
        if _banner(summary) == "official"
        else "EOD evidence is degraded but usable."
        if _banner(summary) == "degraded"
        else "EOD evidence is blocked and must not be published as official."
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8"><title>EOD Auto Repair Report</title></head><body>\n'
        f'<header data-status="{_banner(summary)}"><h1>EOD Auto Repair Report</h1>'
        f"<p>{text(_banner(summary))}</p></header>\n"
        "<main>\n"
        "<section><h2>Run identity</h2><dl>"
        f"<dt>EOD run ID</dt><dd>{text(context['eod_run_id'])}</dd>"
        f"<dt>Strategy cohort run ID</dt><dd>{text(context['strategy_run_id'])}</dd>"
        f"<dt>Trade date</dt><dd>{text(summary.trade_date)}</dd>"
        f"<dt>Final status</dt><dd>{text(summary.final_status.value)}</dd>"
        f"<dt>Remaining blockers</dt><dd>{text(blocker_text)}</dd>"
        "</dl></section>\n"
        f"<section><h2>Data and check stages</h2><ul>{check_items}</ul></section>\n"
        f"<section><h2>Strategy publications</h2><ul>{publication_items}</ul></section>\n"
        "<section><h2>Browser acceptance</h2>"
        f"<p>Status: {text(context['browser_status'])}</p>"
        f"<p>Repair action: {text(action.get('name') or 'none')} — {text(action.get('message') or 'none')}</p>"
        f"<ul>{attempt_items}</ul><p>Rerun result: {text(rerun_text)}</p></section>\n"
        f"<section><h2>Evidence links</h2><ul>{link_items}</ul></section>\n"
        f"<section><h2>Infrastructure issues</h2><ul>{issue_items}</ul></section>\n"
        f"<section><h2>Final decision</h2><p>{text(decision)}</p></section>\n"
        "</main></body></html>\n"
    )


def _safe_output_dir(output_dir: str | Path) -> Path:
    output = Path(output_dir)
    if output.exists() and output.is_symlink():
        raise ValueError(f"report output directory must not be a symlink: {output}")
    output.mkdir(parents=True, exist_ok=True)
    resolved = output.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"report output is not a directory: {output}")
    return resolved


def _atomic_private_write(output_dir: Path, name: str, content: bytes) -> None:
    target = output_dir / name
    try:
        target.relative_to(output_dir)
    except ValueError as exc:
        raise ValueError(f"report path escapes output directory: {target}") from exc
    fd, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=output_dir)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _report_failure(summary: RepairRunSummary, issue: str) -> RepairRunSummary:
    return replace(
        summary,
        final_status=RepairStatus.FAILED,
        infrastructure_issues=[*summary.infrastructure_issues, issue],
    )


def write_summary_files(
    summary: RepairRunSummary,
    output_dir: str | Path,
    *,
    html_renderer: Callable[[RepairRunSummary, str | Path], str] | None = None,
) -> RepairRunSummary:
    output = _safe_output_dir(output_dir)
    selected_html_renderer = html_renderer or render_html_report
    _atomic_private_write(output, "run_summary.json", summary_json_bytes(summary))
    markdown = render_markdown_report(summary, output)
    _atomic_private_write(output, "run_report.md", markdown.encode("utf-8"))
    try:
        html = selected_html_renderer(summary, output)
        _atomic_private_write(output, "run_report.html", html.encode("utf-8"))
    except Exception as exc:
        (output / "run_report.html").unlink(missing_ok=True)
        failed = _report_failure(summary, f"run_report_html_failed:{type(exc).__name__}:{exc}")
        _atomic_private_write(output, "run_summary.json", summary_json_bytes(failed))
        failed_markdown = render_markdown_report(failed, output)
        _atomic_private_write(output, "run_report.md", failed_markdown.encode("utf-8"))
        return failed

    prune_report_retention(output.parent, current_run_dir=output)
    return summary


def _retention_run_ids(payload: JsonObject) -> list[str]:
    run_id_keys = {
        "run_id",
        "runId",
        "eod_run_id",
        "strategy_cohort_run_id",
        "browser_run_id",
    }
    values: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in run_id_keys and isinstance(nested, str) and nested.strip():
                    values.append(nested.strip())
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(payload)
    return values


def _is_initial_baseline_run_id(value: str) -> bool:
    return value == "pv-initial" or value.startswith("pv-initial-")


def _artifact_is_trusted(path_value: str, *, run_dir: Path, browser_dir: Path) -> bool:
    raw = Path(path_value)
    artifact = raw if raw.is_absolute() else run_dir / raw
    try:
        lexical_relative = artifact.relative_to(run_dir)
    except ValueError:
        return False
    current = run_dir
    for part in lexical_relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    if not artifact.is_file():
        return False
    try:
        resolved = artifact.resolve(strict=True)
        resolved.relative_to(run_dir)
        resolved.relative_to(browser_dir)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def prune_report_retention(
    root: str | Path,
    *,
    current_run_dir: str | Path,
    now: datetime | None = None,
    dry_run: bool = False,
) -> list[Path]:
    retention_root = Path(root)
    if not retention_root.exists() or retention_root.is_symlink() or not retention_root.is_dir():
        return []
    root_resolved = retention_root.resolve(strict=True)
    current_resolved = Path(current_run_dir).resolve(strict=False)
    cutoff = (now or datetime.now(timezone.utc)).date() - timedelta(days=90)
    removed: list[Path] = []
    for candidate in sorted(retention_root.iterdir(), key=lambda item: item.name):
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            candidate_date = datetime.strptime(candidate.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if candidate_date.isoformat() != candidate.name or candidate_date >= cutoff:
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root_resolved)
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved == current_resolved:
            continue
        summary_path = resolved / "run_summary.json"
        if summary_path.is_symlink() or not summary_path.is_file():
            continue
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("trade_date") != candidate.name:
            continue
        blockers = payload.get("remaining_blockers")
        if (
            payload.get("final_status") != RepairStatus.SUCCESS.value
            or not isinstance(blockers, list)
            or blockers
        ):
            continue
        browser = payload.get("browser_acceptance")
        if not isinstance(browser, dict):
            continue
        action = browser.get("action")
        check = browser.get("check")
        if not isinstance(action, dict) or not isinstance(check, dict):
            continue
        if action.get("status") != RepairStatus.SUCCESS.value:
            continue
        if check.get("status") != RepairStatus.SUCCESS.value:
            continue
        metadata = payload.get("metadata")
        trusted_baseline = payload.get("trusted_initial_baseline") is True or (
            isinstance(metadata, dict) and metadata.get("trusted_initial_baseline") is True
        )
        run_ids = _retention_run_ids(payload)
        eod_run_id = payload.get("run_id")
        action_metrics = action.get("metrics")
        strategy_run_id = action_metrics.get("run_id") if isinstance(action_metrics, dict) else None
        if not isinstance(eod_run_id, str) or not eod_run_id.strip():
            continue
        if not isinstance(strategy_run_id, str) or not strategy_run_id.strip():
            continue
        if trusted_baseline or any(_is_initial_baseline_run_id(value) for value in run_ids):
            continue
        browser_dir = resolved / "browser"
        reports_exist = all(
            (resolved / name).is_file() and not (resolved / name).is_symlink()
            for name in ("run_summary.json", "run_report.md", "run_report.html")
        )
        if browser_dir.is_symlink() or not browser_dir.is_dir() or not reports_exist:
            continue
        try:
            browser_resolved = browser_dir.resolve(strict=True)
            browser_resolved.relative_to(resolved)
        except (OSError, RuntimeError, ValueError):
            continue
        artifact_paths = action.get("artifact_paths")
        if not isinstance(artifact_paths, list) or not artifact_paths:
            continue
        if not all(
            isinstance(path_value, str)
            and path_value
            and _artifact_is_trusted(
                path_value,
                run_dir=resolved,
                browser_dir=browser_resolved,
            )
            for path_value in artifact_paths
        ):
            continue
        removed.append(candidate)
        if not dry_run:
            shutil.rmtree(resolved)
    return removed
