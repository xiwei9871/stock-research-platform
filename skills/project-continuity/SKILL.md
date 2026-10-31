---
name: project-continuity
description: Recover and maintain project truth across sessions — state files, decision register, evidence gates. Use at session start on this repo.
---

# Project Continuity

Git is the memory. Chat is not. At session start:

1. `git status --short --branch` then read
   `docs/agent_governance/{PROJECT_STATE.yaml,DECISIONS.md,HANDOFF.md}`
2. Run `python3 tools/gov/sr_gates.py all` before reporting status
3. ACTIVE decisions in DECISIONS.md block conflicting requests — say so
4. Report Build/Tests/Deploy separately; unverified ⇒ NOT_VERIFIED, never inherited
5. Before handoff: update PROJECT_STATE.yaml + HANDOFF.md, commit
6. Forbidden: prod deploy without approval, parallel baostock sessions,
   deleting protected outputs/, cron pointing off `main`
