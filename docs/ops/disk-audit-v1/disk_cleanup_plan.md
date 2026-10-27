# Disk Cleanup Plan — pending owner approval (DRY RUN, nothing executed)

Date: 2026-10-27. Data volume: 193.8G used / ~8-11G free (96-97%). Tonight
20:30-22:15 is the EOD hotfix live run — do NOT disturb stock_research or
system services tonight.

## Order of operations (when approved)

### Tier 1 — trivial, ~2.4G reclaim (no real risk)
1. `~/Library/Caches/*` rebuildable caches — ~1.2G
2. `~/Library/Application Support/Google/GoogleUpdater/crx_cache/*` — ~0.7G
3. `~/.gradle/caches` — ~1.5G (rebuilds on next gradle run)
4. Playwright browser cache — ~0.2G (auto re-downloads)

### Tier 2 — the big wins, ~12-21G (requires owner decision)
5. **claudevm.bundle 12G** — delete ONLY after confirming no active claude
   session: `pgrep -fl 'claude.*vm|Claude-3p'` empty AND rootfs.img mtime
   stale >1h. Recreates itself on next use.
6. **statcan raw CSVs ~9.9G** — first verify `data/research/macro/{master,out}`
   already contain the needed derived series (they were written 11:28, after
   the 10:37 raw). Options in order of safety:
   a. gzip the raw CSVs in place (~9.9G → ~1.2G) — reversible, keeps data
   b. delete expanded CSVs, keep the .zip sources (re-expandable)
   c. delete all, re-download from statcan.gc.ca if needed (slowest)
   Recommendation: (a) — keeps evidence, saves ~8.7G.

### Tier 3 — maintenance, ~1-2G (needs app stopped)
7. devin sessions.db `VACUUM`/old-session prune — only while cli not running.
8. codex archived_sessions prune — owner previously opted to keep; skip
   unless asked.

### Explicitly NOT proposed
- northshore sqlite (research DB), interior_design (frozen), stock_research
  (tonight's live EOD), Chaos/V-Ray, codex sessions, .Spotlight/system dirs
  (root-managed — run the sudo du first, do not rm).

## Rollback / safety
- Tier 1-2 items are all regenerable or compressed-in-place; nothing here is
  unrecoverable except the VM bundle (which self-recreates).
- gzip replacement pattern from the earlier storage governance run
  (`gzip_safe.sh` in storage-governance-v1) is reusable for the statcan CSVs —
  hash-verify then atomic replace.
- Total projected reclaim: ~11-21G depending on Tier-2 choices, plus whatever
  the sudo du finds in system space.
