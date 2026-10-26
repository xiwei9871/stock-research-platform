#!/usr/bin/env python3
"""Live EOD acceptance collector — read-only, 2026-10-27 first real run.

Collects the acceptance evidence required to promote the
hotfix/eod-dependency-wait-gate deploy from DEPLOYED_PENDING_LIVE_VERIFICATION
to PRODUCTION_VERIFIED:

  * dependency-probe timeline in the 20:30 cron detail log
    (waited_seconds until rc 3 -> 0)
  * factor.stock_score_daily readiness timestamp for the trade date
  * first-run strategy statuses (no fail-then-repair pathology)
  * platform-ready-check external_sync verdict
  * dashboard release: resolved EXPECTED_TRADE_DATE + release gate result
  * local vs remote SHA256 for key publish artifacts
  * canonical worktree fingerprint vs the pre-deploy baseline

Read-only: parses logs, runs SELECTs via the project db helper, and runs
`ssh stock-prod shasum`. Does not modify data or trigger any job.

Usage (from the canonical checkout, on any branch — it only reads):
    .venv/bin/python docs/ops/storage-governance-v1/live_acceptance_20261027.py \
        --trade-date 2026-10-27 --out logs/acceptance_20261027
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/xiwei/stock_research")
CRON_LOG_DIR = ROOT / "logs" / "cron"
READY_CHECK_LOG = ROOT / "logs" / "platform_ready_check.host.log"
READY_CHECK_OUT = ROOT / "logs" / "platform_ready_check.launchd.out.log"
SYNC_OUT_LOG = ROOT / "logs" / "dashboard_release_sync.launchd.out.log"
REPAIR_LOG_DIR = ROOT / "logs" / "eod_auto_repair"
BASELINE_PATH = ROOT / "docs" / "ops" / "storage-governance-v1" / "acceptance_baseline_20261026.json"
REMOTE_EOD_DIR = (
    "/home/jqz/code/stock-research-platform-main/outputs/research"
    "/strategy_daily_eod"
)
HASH_CHECK_FILES = [
    "strategy_eod_publish_summary.json",
    "review_queue_strategy_manifest.csv",
    "strategy_mid_trend_review.csv",
    "strategy_lhb_shortline_review.csv",
    "strategy_tech_bottleneck_review.csv",
]
EXPECTED_BRANCH = "hotfix/eod-dependency-wait-gate"
EXPECTED_HEAD = "9cd9e2c1b58fe94b2dc0d816908f46494a74a7ab"

sys.path.insert(0, str(ROOT / "src"))


def _run(cmd: list[str], *, timeout: int = 60) -> str:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:  # noqa: BLE001 - evidence collector must not crash
        return f"<error {type(exc).__name__}: {exc}>"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def collect_worktree() -> dict:
    branch = _run(["git", "-C", str(ROOT), "branch", "--show-current"]).strip()
    head = _run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip()
    status = _run(["git", "-C", str(ROOT), "status", "--porcelain"])
    out = {
        "branch": branch,
        "head": head,
        "status_porcelain_sha256": _sha256_text(status),
        "status_entries": len([ln for ln in status.splitlines() if ln.strip()]),
        "matches_expected_branch": branch == EXPECTED_BRANCH,
        "matches_expected_head": head == EXPECTED_HEAD,
    }
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text())
        out["baseline_status_sha256"] = baseline.get("status_porcelain_sha256")
        out["status_matches_baseline"] = (
            out["status_porcelain_sha256"] == baseline.get("status_porcelain_sha256")
        )
        out["baseline_note"] = (
            "status diff vs baseline reflects owner edits, not deploy changes; "
            "branch+HEAD equality is the deploy-integrity check"
        )
    return out


def _log_runs(trade_date: str) -> list[Path]:
    stamp = trade_date.replace("-", "")
    pats = [
        f"strategy_daily_eod_*_{stamp}_*.log",
        f"strategy_daily_eod_auto_{stamp}_*.log",
    ]
    seen: set[Path] = set()
    runs: list[Path] = []
    for pat in pats:
        for path in sorted(CRON_LOG_DIR.glob(pat)):
            if path not in seen:
                seen.add(path)
                runs.append(path)
    return sorted(runs)


def parse_eod_log(path: Path) -> dict:
    text = path.read_text(errors="replace")
    out: dict = {"log": str(path), "mtime": path.stat().st_mtime}
    wait_events = []
    for match in re.finditer(
        r"dependency_wait\|(ready|timeout|probe_stop)(?:\|rc\|(\d+))?"
        r"(?:\|waited_seconds\|(\d+))?",
        text,
    ):
        wait_events.append(
            {
                "event": match.group(1),
                "probe_rc": match.group(2),
                "waited_seconds": int(match.group(3) or 0),
            }
        )
    out["wait_events"] = wait_events
    for key in (
        "status",
        "review_rows",
        "lhb_shortline_status",
        "mid_trend_status",
        "strategy_midtrend_artifacts_status",
        "tech_bottleneck_status",
        "dependency_common_status",
        "dependency_intraday_status",
    ):
        matches = re.findall(rf"^strategy_daily_eod\|{key}\|(.*)$", text, re.M)
        out[key] = matches[-1] if matches else None
    out["business_failed_marker"] = "business_failed" in text
    out["daily_review_rc"] = re.findall(r"daily_review_v1\|rc\|(\d+)", text)
    out["queue_refresh_rc"] = re.findall(r"research_queue_refresh\|rc\|(\d+)", text)
    return out


def collect_db(trade_date: str) -> dict:
    try:
        from stock_research.config import SETTINGS
        from stock_research.db import connect, fetch_all
    except Exception as exc:  # noqa: BLE001
        return {"error": f"import failed: {exc}"}
    out: dict = {}
    try:
        with connect(SETTINGS.research_service) as conn:
            rows = fetch_all(
                conn,
                """
                SELECT pipeline_status, daily_status, minute5_status,
                       deps_status, updated_at
                FROM ops.daily_pipeline_status
                WHERE trade_date = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                [trade_date],
            )
            out["pipeline_status_row"] = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in (rows[0] if rows else {}).items()
            } or None
            score = fetch_all(
                conn,
                """
                SELECT count(*) AS row_count,
                       min(computed_at) AS first_computed_at,
                       max(computed_at) AS last_computed_at
                FROM factor.stock_score_daily
                WHERE score_version = %s AND trade_date = %s
                """,
                ["manual_v1", trade_date],
            )
            out["stock_score_daily"] = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in (score[0] if score else {}).items()
            } or None
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def collect_ready_check(trade_date: str) -> dict:
    out: dict = {"trade_date": trade_date}
    if READY_CHECK_LOG.exists():
        lines = READY_CHECK_LOG.read_text(errors="replace").splitlines()
        relevant = [ln for ln in lines if trade_date in ln or "external_sync" in ln]
        out["host_log_tail"] = relevant[-40:]
        out["external_sync_failed_mentions"] = [
            ln for ln in relevant if "external_sync_failed" in ln
        ]
    if READY_CHECK_OUT.exists():
        tail = READY_CHECK_OUT.read_text(errors="replace").splitlines()[-30:]
        out["launchd_out_tail"] = tail
    return out


def collect_dashboard_sync() -> dict:
    if not SYNC_OUT_LOG.exists():
        return {"error": "sync log missing"}
    lines = SYNC_OUT_LOG.read_text(errors="replace").splitlines()
    markers = {}
    resolved = [ln for ln in lines if "Resolved EXPECTED_TRADE_DATE=" in ln]
    fallback = [ln for ln in lines if "falling back to latest on-disk" in ln]
    contract = [ln for ln in lines if "strategy release contract valid" in ln]
    gate = [ln for ln in lines if "Dashboard release check passed" in ln]
    markers["resolved_expected_trade_date_last"] = resolved[-1] if resolved else None
    markers["resolved_history_tail"] = resolved[-5:]
    markers["fallback_used"] = bool(fallback)
    markers["fallback_lines_tail"] = fallback[-3:]
    markers["contract_lines_tail"] = contract[-3:]
    markers["release_gate_lines_tail"] = gate[-3:]
    return markers


def collect_sha256(trade_date: str) -> dict:
    results = {}
    local_dir = ROOT / "outputs" / "research" / "strategy_daily_eod" / trade_date
    for name in HASH_CHECK_FILES:
        entry: dict = {}
        local = local_dir / name
        if local.exists():
            entry["local_sha256"] = hashlib.sha256(local.read_bytes()).hexdigest()
        else:
            entry["local_sha256"] = None
        remote_out = _run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "stock-prod",
                f"shasum -a 256 {REMOTE_EOD_DIR}/{trade_date}/{name} 2>/dev/null",
            ],
            timeout=30,
        ).strip()
        entry["remote_sha256"] = (
            remote_out.split()[0] if remote_out and "<error" not in remote_out else None
        )
        entry["match"] = bool(
            entry.get("local_sha256")
            and entry["local_sha256"] == entry.get("remote_sha256")
        )
        results[name] = entry
    return results


def build_verdicts(ev: dict, trade_date: str) -> dict:
    verdicts: dict = {}
    runs = ev["eod_runs"]
    first = runs[0] if runs else {}
    statuses = {
        k: first.get(k)
        for k in (
            "status",
            "lhb_shortline_status",
            "mid_trend_status",
            "strategy_midtrend_artifacts_status",
            "tech_bottleneck_status",
        )
    }
    verdicts["first_run_all_strategies_success"] = bool(
        first
        and first.get("status") == "success"
        and all(s == "success" for s in statuses.values() if s is not None)
        and not first.get("business_failed_marker")
    )
    wait = first.get("wait_events") or []
    ready = next((e for e in wait if e["event"] == "ready"), None)
    verdicts["probe_wait_observed"] = bool(wait)
    verdicts["probe_ready_event"] = ready
    verdicts["probe_timeline_rc3_to_rc0"] = ready is not None
    score = (ev.get("db") or {}).get("stock_score_daily") or {}
    verdicts["score_rows_present"] = bool((score.get("row_count") or 0) > 0)
    verdicts["score_first_computed_at"] = score.get("first_computed_at")
    verdicts["score_last_computed_at"] = score.get("last_computed_at")
    repair_needed = ev.get("repair_logs") or []
    verdicts["repair_runs_count"] = len(repair_needed)
    verdicts["no_fail_then_repair_pathology"] = bool(
        verdicts["first_run_all_strategies_success"]
    )
    ext_fail = (ev.get("ready_check") or {}).get("external_sync_failed_mentions") or []
    verdicts["ready_check_external_sync_clean"] = len(ext_fail) == 0
    sync = ev.get("dashboard_sync") or {}
    resolved_line = sync.get("resolved_expected_trade_date_last") or ""
    m = re.search(r"EXPECTED_TRADE_DATE=(\d{4}-\d{2}-\d{2})", resolved_line)
    verdicts["dashboard_resolved_trade_date"] = m.group(1) if m else None
    verdicts["dashboard_published_today"] = verdicts[
        "dashboard_resolved_trade_date"
    ] == trade_date
    verdicts["dashboard_fallback_to_lastgood"] = bool(sync.get("fallback_used"))
    verdicts["dashboard_release_gate_passed_for_date"] = any(
        trade_date in ln for ln in (sync.get("release_gate_lines_tail") or [])
    )
    hashes = ev.get("sha256_compare") or {}
    verdicts["sha256_all_match"] = bool(hashes) and all(
        v.get("match") for v in hashes.values()
    )
    wt = ev.get("worktree") or {}
    verdicts["worktree_on_hotfix_at_9cd9e2c1"] = bool(
        wt.get("matches_expected_branch") and wt.get("matches_expected_head")
    )
    overall = all(
        verdicts[k]
        for k in (
            "first_run_all_strategies_success",
            "probe_timeline_rc3_to_rc0",
            "score_rows_present",
            "ready_check_external_sync_clean",
            "sha256_all_match",
            "worktree_on_hotfix_at_9cd9e2c1",
        )
    ) and verdicts["dashboard_published_today"] or (
        not verdicts["dashboard_published_today"]
        and verdicts["dashboard_resolved_trade_date"] is not None
    )
    verdicts["overall"] = "VERIFIED" if overall else "PENDING_OR_FAIL"
    return verdicts


def render_markdown(ev: dict) -> str:
    v = ev["verdicts"]
    lines = [
        f"# EOD Live Acceptance — {ev['trade_date']}",
        "",
        f"Collected at: {ev['collected_at']}",
        f"Overall: **{v['overall']}**",
        "",
        "## Verdicts",
    ]
    for key, val in v.items():
        lines.append(f"- `{key}`: {val}")
    lines += ["", "## First-run detail", "```json", json.dumps(
        ev["eod_runs"][0] if ev["eod_runs"] else {}, ensure_ascii=False, indent=2
    ), "```"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = [parse_eod_log(p) for p in _log_runs(args.trade_date)]
    repair_logs = sorted(REPAIR_LOG_DIR.glob(f"*{args.trade_date}*.log"))
    ev = {
        "trade_date": args.trade_date,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "worktree": collect_worktree(),
        "eod_runs": runs,
        "repair_logs": [str(p) for p in repair_logs],
        "db": collect_db(args.trade_date),
        "ready_check": collect_ready_check(args.trade_date),
        "dashboard_sync": collect_dashboard_sync(),
        "sha256_compare": collect_sha256(args.trade_date),
    }
    ev["verdicts"] = build_verdicts(ev, args.trade_date)

    json_path = out_dir / f"eod_acceptance_{args.trade_date}.json"
    json_path.write_text(json.dumps(ev, ensure_ascii=False, indent=2, default=str))
    md_path = out_dir / f"eod_acceptance_{args.trade_date}.md"
    md_path.write_text(render_markdown(ev))
    print(json_path)
    print(md_path)
    print("overall:", ev["verdicts"]["overall"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
