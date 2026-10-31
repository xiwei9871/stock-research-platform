#!/usr/bin/env python3
"""stock-research-platform governance gates — read-only, no credentials."""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "docs/agent_governance/PROJECT_STATE.yaml")
GOV_PREFIX = "chore/"

PROTECTED_OUTPUTS = [
    "outputs/research/serenity_bottleneck_baseline_st_only_financial_state_20250101_20260605",
    "outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260605",
    "outputs/research/market_emotion_state_v1_20230103_20260605",
    "outputs/research/mid_trend_watch_funnel_detail.csv",
    "outputs/research/strategy_daily_eod",
]
REJECTED = [
    (r"max_workers_baostock_minute5\s*=\s*([2-9]|\d\d+)", "D03 parallel baostock forbidden"),
    (r"rm\s+-rf\s+[^\n]*outputs/research", "D04 protected outputs deletion"),
    (r"workers\s*=\s*([2-9]|\d\d+)[^\n]*baostock|baostock[^\n]*workers\s*=\s*([2-9]|\d\d+)", "D03 baostock workers>1"),
]


def sh(*a):
    return subprocess.run(a, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def gate_state_head():
    if not os.path.exists(STATE):
        return [("state-head", "FAIL", "PROJECT_STATE.yaml missing")]
    txt = open(STATE).read()
    m = re.search(r"head_commit:\s*([0-9a-f]{7,40})", txt)
    bm = re.search(r"^\s*branch:\s*(\S+)", txt, re.M)
    if not m or not bm:
        return [("state-head", "FAIL", "state file missing head_commit/branch")]
    rec, bbr = m.group(1), bm.group(1)
    head = sh("git", "rev-parse", "HEAD")
    cur = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    if head.startswith(rec) or rec.startswith(head):
        return [("state-head", "PASS", f"on recorded baseline {rec[:7]}")]
    base = sh("git", "merge-base", "HEAD", rec)
    if base.startswith(rec) or rec.startswith(base):
        tag = "governance/descendant branch — baseline intact" if cur != bbr else "recorded commit is ancestor — update PROJECT_STATE.yaml"
        ok = cur != bbr
        return [("state-head", "PASS" if ok else "FAIL", f"{tag} (on {cur})")]
    return [("state-head", "FAIL", f"HEAD {head[:7]} diverged from recorded {rec[:7]}")]


def gate_workspace():
    dirty = [l for l in sh("git", "status", "--porcelain").splitlines() if l.strip()]
    if dirty:
        return [("state-workspace", "PASS", f"{len(dirty)} uncommitted change(s) — commit before handoff")]
    return [("state-workspace", "PASS", "clean")]


def gate_protected_outputs():
    missing = [p for p in PROTECTED_OUTPUTS if not os.path.exists(os.path.join(ROOT, p))]
    if missing:
        return [("protected-inputs", "FAIL", "missing runtime inputs: " + ", ".join(missing))]
    return [("protected-inputs", "PASS", f"{len(PROTECTED_OUTPUTS)} protected inputs present")]


def gate_decisions():
    hits = []
    for dirpath, _dirs, files in os.walk(ROOT):
        for fn in files:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT)
            if rel.startswith((".git", "node_modules", ".venv", "tools/gov", "docs/agent_governance",
                               "logs", "outputs", "tests", "reports", "data", ".worktrees")):
                continue
            if os.path.getsize(p) > 2_000_000:
                continue
            try:
                txt = open(p, errors="ignore").read()
            except OSError:
                continue
            for pat, label in REJECTED:
                if re.search(pat, txt):
                    hits.append(f"{rel}: {label}")
    if hits:
        return [("assets-decisions", "FAIL", "; ".join(hits[:5]))]
    return [("assets-decisions", "PASS", "no rejected patterns in tracked code")]


def gate_report():
    # Evidence-first: PASS only with traceable artifact evidence.
    ev = []
    for pat in ("docs/**/*report*.md", "docs/**/test-results*.json"):
        ev += subprocess.run(["find", "docs", "-name", "*report*", "-o", "-name", "test-results*"],
                             cwd=ROOT, capture_output=True, text=True).stdout.split()
    build = "NOT_VERIFIED"
    return [("report-build", build, "no build artifact SHA recorded — backend is interpreted; see tests"),
            ("report-tests", "NOT_VERIFIED", "run .venv/bin/pytest then record result in PROJECT_STATE.yaml"),
            ("report-deploy", "NOT_VERIFIED", "external deploy requires explicit approval + launchd run")]


def gate_deploy_preflight():
    return [("deploy-auth", "BLOCKED", "deploy always requires explicit human authorization (D07)")]


def self_test():
    res = []
    res.append(("T01 protected-outputs gate runnable", len(gate_protected_outputs()) == 1))
    r = gate_report()
    res.append(("T02 report is NOT_VERIFIED without evidence", all(x[1] == "NOT_VERIFIED" for x in r)))
    res.append(("T03 deploy always blocked", gate_deploy_preflight()[0][1] == "BLOCKED"))
    return res


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        rows = gate_state_head() + gate_workspace() + gate_protected_outputs() + gate_decisions()
    elif cmd == "report":
        rows = gate_report()
    elif cmd == "deploy":
        rows = gate_deploy_preflight()
    elif cmd == "self-test":
        rows = [("self-test", "PASS" if ok else "FAIL", name) for name, ok in self_test()]
    else:
        print(__doc__); return 2
    for name, status, detail in rows:
        print(f"{status:4s}  {name:24s} {detail}")
    return 0 if all(s != "FAIL" for _n, s, _d in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
