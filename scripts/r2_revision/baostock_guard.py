"""Pre-flight guard for baostock operations.

Baostock allows exactly ONE session per host — concurrent logins cause
`10002007` and rapid session churn triggers the `10001011` blacklist.
Before any script opens `bs.login()`, it MUST verify:

1. no other process is running a known baostock-using script, and
2. no process holds an ESTABLISHED TCP connection to the baostock server.

`assert_baostock_free()` exits non-zero with a clear message if either
check fails — call it immediately before bs.login().
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys

# script basenames known to open baostock sessions; extend as needed
BAOSTOCK_SCRIPT_PATTERNS = (
    "r2_repair_batch.py", "r2_repair_driver.py", "r2_classify_batch.py",
    "r2_review_verify.py", "r2_live_diff.py", "r2_batch_dry",
    "minute_backfill", "minute5", "baostock",
)


def baostock_processes(exclude_pid: int | None = None) -> list[str]:
    """Live processes whose cmdline references a baostock-using script."""
    me = exclude_pid or os.getpid()
    out = subprocess.run(
        ["ps", "-eo", "pid=,comm=,args="], capture_output=True, text=True)
    hits = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        comm, cmd = parts[1], parts[2]
        if pid == me or pid == os.getppid():
            continue
        # executable must actually be python — bash wrappers that merely
        # mention script paths (e.g. nohup bash -c ...) are not sessions
        if not comm.lower().startswith("python"):
            continue
        if any(p in cmd for p in BAOSTOCK_SCRIPT_PATTERNS):
            hits.append(line[:160])
    return hits


def baostock_endpoint() -> tuple[str, int]:
    """Endpoint actually used by the installed baostock client —
    read its own constants instead of guessing."""
    try:
        import baostock.common.contants as cons
        return cons.BAOSTOCK_SERVER_IP, int(cons.BAOSTOCK_SERVER_PORT)
    except Exception:
        return "public-api.baostock.com", 10030


def baostock_connections() -> list[str]:
    """ESTABLISHED TCP sessions to the real baostock service endpoint."""
    host, port = baostock_endpoint()
    try:
        ips = {ai[4][0] for ai in socket.getaddrinfo(
            host, port, socket.AF_INET)}
    except socket.gaierror:
        return []
    out = subprocess.run(
        ["lsof", "-nP", "-iTCP", "-sTCP:ESTABLISHED"],
        capture_output=True, text=True)
    hits = []
    for line in out.stdout.splitlines():
        if any(f"->{ip}:{port}" in line for ip in ips):
            hits.append(line.strip()[:160])
    return hits


def assert_baostock_free(exclude_pid: int | None = None) -> None:
    procs = baostock_processes(exclude_pid)
    conns = baostock_connections()
    if procs or conns:
        for h in procs:
            print(f"!! stale baostock process: {h}", flush=True)
        for h in conns:
            print(f"!! open baostock connection: {h}", flush=True)
        sys.exit("FATAL: baostock session already in use — "
                 "single-worker constraint violated; kill stale "
                 "processes before login")


BLACKLIST_CODES = ("10001011", "黑名单")


def is_blacklist_error(text: str) -> bool:
    return any(c in (text or "") for c in BLACKLIST_CODES)


def controlled_login_probe() -> bool:
    """Single login + logout probe. Returns True if baostock accepts us.
    Used after a suspected unblock — never loops, one attempt only."""
    import baostock as bs
    r = bs.login()
    if r.error_code != "0":
        print(f"probe login failed {r.error_code} {r.error_msg}", flush=True)
        return False
    bs.logout()
    print("probe login OK", flush=True)
    return True
