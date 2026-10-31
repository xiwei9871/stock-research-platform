#!/usr/bin/env python3
"""Emit Devin hook additionalContext: a one-screen project-state digest.

Read-only. Prints a JSON hookSpecificOutput object on stdout, or nothing
if the state file is absent (hook must never crash a session).
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "docs/agent_governance/PROJECT_STATE.yaml")

KEEP = re.compile(
    r"^(  branch|  head_commit|  version|  phase|  offset|  size|  end"
    r"|  app_size_bytes|    device_tests|  human_gate|  next_safe_action"
    r"|  build|  host_tests|  device_tests)\s*:")


def main():
    if not os.path.exists(STATE):
        return
    lines = [l for l in open(STATE).read().splitlines() if KEEP.match(l)]
    br = subprocess.run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
    ctx = ("AF PROJECT STATE (authoritative file: "
           "docs/agent_governance/PROJECT_STATE.yaml)\n"
           f"current checkout: {br}\n" + "\n".join(lines) +
           "\nRules: DECISIONS.md ACTIVE entries may not be silently "
           "violated. Build/Host PASS != Device PASS.")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": ctx}}))


if __name__ == "__main__":
    main()
