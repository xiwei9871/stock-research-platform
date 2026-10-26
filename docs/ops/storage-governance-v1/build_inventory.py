#!/usr/bin/env python3
"""Storage governance V1 — inventory + reference scan for ~/stock_research.

Read-only. Emits:
  inventory.csv         one row per audited entry
  references_hits.csv   basename -> referencing code files
  dup_groups.csv        sha256 -> files >10MB sharing identical content
"""
import csv, hashlib, os, re, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path("/Users/xiwei/stock_research")
OUT = ROOT / "docs/ops/storage-governance-v1"
OUT.mkdir(parents=True, exist_ok=True)

ENTRY_SCOPES = ["outputs/research", "outputs", "data", "logs", "reports",
                "artifacts", "cache", "build"]
AGGREGATE_ONLY = ["dashboard", "src", "tests", "docs", "scripts", "config",
                  "deploy", ".venv", ".git", "research"]
SCAN_CODE_DIRS = ["src", "scripts", "config", "deploy", "docs", "tests",
                  "dashboard/src", "tools", "artifacts"]
EXTRA_CODE_FILES = ["AGENTS.md", "README.md", "pyproject.toml"]
SKIP_SCAN = {".venv", ".git", "node_modules", "__pycache__", ".next",
             "storage-governance-v1"}
MIN_DUP_SIZE = 10 * 1024 * 1024  # >10MB

PROTECTED = {
    "outputs/research/serenity_bottleneck_baseline_st_only_financial_state_20250101_20260605",
    "outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260605",
    "outputs/research/market_emotion_state_v1_20230103_20260605",
    "outputs/research/mid_trend_watch_funnel_detail.csv",
    "outputs/research/strategy_daily_eod",
    "reports",
}

def dir_stats(p: Path):
    total = 0; nfiles = 0; mtmax = 0; mtmin = 0; exts = defaultdict(int)
    try:
        for dp, dns, fns in os.walk(p, followlinks=False):
            dns[:] = [d for d in dns if d not in SKIP_SCAN]
            for fn in fns:
                fp = Path(dp) / fn
                try:
                    st = fp.lstat()
                except OSError:
                    continue
                total += st.st_size; nfiles += 1
                mtmax = max(mtmax, st.st_mtime)
                mtmin = min(mtmin, st.st_mtime) if mtmin else st.st_mtime
                exts[fp.suffix.lower() or "(none)"] += st.st_size
    except OSError:
        pass
    return total, nfiles, mtmax, mtmin, exts

def fmt_types(exts, top=4):
    return ";".join(f"{e}:{b/1048576:.0f}MB" for e, b in
                    sorted(exts.items(), key=lambda x: -x[1])[:top])

entries = {}
for scope in ENTRY_SCOPES:
    sp = ROOT / scope
    if not sp.is_dir():
        continue
    for child in sorted(sp.iterdir()):
        if child.name.startswith(".") or child.name in SKIP_SCAN:
            continue
        rel = child.relative_to(ROOT).as_posix()
        if child.is_symlink():
            entries[rel] = dict(kind="symlink", size=0, nfiles=0,
                                mtmax=child.lstat().st_mtime, mtmin=0, exts={})
        elif child.is_dir():
            s, n, mx, mn, ex = dir_stats(child)
            entries[rel] = dict(kind="dir", size=s, nfiles=n,
                                mtmax=mx, mtmin=mn, exts=ex)
        else:
            st = child.lstat()
            entries[rel] = dict(kind="file", size=st.st_size, nfiles=1,
                                mtmax=st.st_mtime, mtmin=st.st_mtime,
                                exts={child.suffix.lower(): st.st_size})
for d in AGGREGATE_ONLY:
    p = ROOT / d
    if not p.exists():
        continue
    s, n, mx, mn, ex = dir_stats(p)
    entries[d] = dict(kind="dir_agg", size=s, nfiles=n, mtmax=mx, mtmin=mn, exts=ex)

# ---- reference scan: collect basenames mentioned in code/config/docs ----
basenames = {Path(r).name for r in entries if "/" in r}
pattern = re.compile(rb"[A-Za-z0-9_][A-Za-z0-9_.\-]{7,}")
ref_hits = defaultdict(set)
scan_files = []
for d in SCAN_CODE_DIRS:
    dp = ROOT / d
    if not dp.is_dir():
        continue
    for p in dp.rglob("*"):
        if p.is_file() and not any(s in p.parts for s in SKIP_SCAN):
            scan_files.append(p)
for f in EXTRA_CODE_FILES:
    p = ROOT / f
    if p.is_file():
        scan_files.append(p)
for p in scan_files:
    try:
        data = p.read_bytes()
    except OSError:
        continue
    if b"\0" in data[:8192]:
        continue
    rel = p.relative_to(ROOT).as_posix()
    for m in pattern.finditer(data):
        tok = m.group().decode("utf-8", "ignore")
        if tok in basenames:
            ref_hits[tok].add(rel)
with open(OUT / "references_hits.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["basename", "referenced_in"])
    for k in sorted(ref_hits):
        w.writerow([k, "|".join(sorted(ref_hits[k]))])

# ---- duplicate detection >10MB ----
hashes = defaultdict(list)
for rel, e in entries.items():
    p = ROOT / rel
    if e["kind"] == "file" and e["size"] >= MIN_DUP_SIZE:
        try:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            hashes[h].append((rel, e["size"]))
        except OSError:
            pass
    elif e["kind"] == "dir":
        for dp, dns, fns in os.walk(p, followlinks=False):
            dns[:] = [d for d in dns if d not in SKIP_SCAN]
            for fn in fns:
                fp = Path(dp) / fn
                try:
                    if fp.stat().st_size >= MIN_DUP_SIZE:
                        h = hashlib.sha256(fp.read_bytes()).hexdigest()
                        hashes[h].append((fp.relative_to(ROOT).as_posix(),
                                          fp.stat().st_size))
                except OSError:
                    pass
with open(OUT / "dup_groups.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["sha256", "path", "size_bytes"])
    for h, items in sorted(hashes.items(), key=lambda x: -len(x[1])):
        if len(items) > 1:
            for rel, sz in items:
                w.writerow([h[:16], rel, sz])

now = __import__("time").time()
def age_days(mt):
    return round((now - mt) / 86400, 1) if mt else ""

with open(OUT / "inventory.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["path", "kind", "size_bytes", "size_mb", "file_count",
                "mtime_max_age_days", "mtime_min_age_days", "top_types",
                "protected", "referenced_in_code", "ref_files"])
    for rel in sorted(entries):
        e = entries[rel]
        base = Path(rel).name
        prot = any(rel == pr or rel.startswith(pr + "/") for pr in PROTECTED)
        refs = ref_hits.get(base, set())
        w.writerow([rel, e["kind"], e["size"], f"{e['size']/1048576:.1f}",
                    e["nfiles"], age_days(e["mtmax"]), age_days(e["mtmin"]),
                    fmt_types(e["exts"]), "Y" if prot else "",
                    "Y" if refs else "", "|".join(sorted(refs))[:300]])

total = sum(e["size"] for e in entries.values())
print(f"entries={len(entries)} total={total/1073741824:.2f}GiB "
      f"referenced={len(ref_hits)} dup_groups_written")
