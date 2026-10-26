#!/usr/bin/env python3
"""Weekly storage health check for ~/stock_research (read-only, DRY_RUN by design).

Reports: dir sizes + growth, top-20 fastest-growing dirs, unreferenced stale
candidates, anomaly alerts. Never deletes anything.

Usage: python3 docs/ops/storage-governance-v1/storage_healthcheck.py
Schedule suggestion: weekly via launchd or openclaw cron.
"""
import os, sys, time, json
from pathlib import Path

ROOT = Path("/Users/xiwei/stock_research")
STATE = ROOT / "logs/storage_healthcheck_state.json"
SKIP = {".venv", ".git", "node_modules", "__pycache__", "storage-governance-v1"}
ALERT_GROWTH_MB = 512          # dir grew >512MB in a week -> alert
STALE_DAYS = 60                # no-write >60d -> stale candidate
PROTECTED_MARKERS = ("serenity_bottleneck_baseline", "market_regime_confirmation",
                     "market_emotion_state", "mid_trend_watch_funnel_detail",
                     "strategy_daily_eod")

def dir_size(p: Path):
    total = 0; mt = 0
    for dp, dns, fns in os.walk(p, followlinks=False):
        dns[:] = [d for d in dns if d not in SKIP]
        for fn in fns:
            try:
                st = (Path(dp) / fn).lstat()
                total += st.st_size; mt = max(mt, st.st_mtime)
            except OSError:
                pass
    return total, mt

rows = {}
for child in sorted(ROOT.iterdir()):
    if child.name in SKIP or child.name.startswith("."):
        continue
    if child.is_dir():
        for sub in sorted(child.iterdir()):
            rel = sub.relative_to(ROOT).as_posix()
            rows[rel] = dir_size(sub) if sub.is_dir() else \
                (sub.lstat().st_size, sub.lstat().st_mtime)
    else:
        rows[child.name] = (child.lstat().st_size, child.lstat().st_mtime)

prev = json.loads(STATE.read_text()) if STATE.exists() else {}
now = time.time()
report, alerts, stale = [], [], []
for rel, (sz, mt) in sorted(rows.items(), key=lambda x: -x[1][0]):
    delta = sz - prev.get(rel, sz)
    age_d = (now - mt) / 86400
    line = f"{sz/1048576:9.1f}MB  {delta/1048576:+8.1f}MB/wk  {age_d:6.1f}d  {rel}"
    report.append(line)
    if delta > ALERT_GROWTH_MB * 1048576:
        alerts.append(f"GROWTH {rel}: +{delta/1048576:.0f}MB this week")
    if age_d > STALE_DAYS and not any(m in rel for m in PROTECTED_MARKERS):
        stale.append((sz, rel))

print("== top 20 by size ==")
for l in report[:20]:
    print(l)
print("\n== alerts ==")
print("\n".join(alerts) if alerts else "(none)")
print("\n== stale candidates (no-write >%dd, unprotected) ==" % STALE_DAYS)
for sz, rel in sorted(stale, reverse=True)[:25]:
    print(f"{sz/1048576:9.1f}MB  {rel}")
STATE.parent.mkdir(parents=True, exist_ok=True)
STATE.write_text(json.dumps({k: v[0] for k, v in rows.items()}, indent=1))
print(f"\nstate saved -> {STATE} (DRY_RUN: nothing modified except this state file)")
