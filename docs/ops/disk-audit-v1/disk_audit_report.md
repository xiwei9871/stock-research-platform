# Disk Audit Report V1 — 2026-10-27

## Headline numbers

- Data volume: **193.8 GB consumed / ~8-11 GiB free (96-97%)** — critical
- Accounted in readable space: ~116 GB (user ~80 + system-visible ~36)
- Unaccounted (permission-blocked system space): **~70 GB UNKNOWN** — see
  `system_permission_gaps.md`; needs one `sudo du` to resolve
- 48h confirmed new growth found in readable space: **~23 GB**

## Growth attribution (last 48h, confirmed)

| Source | GB | Evidence |
|---|---|---|
| `Claude-3p/vm_bundles/claudevm.bundle` | **12.0** | created today 14:45, rootfs.img still written 22:22; an active claude-code session (pid 21072) holds it |
| `northshore .../raw/statcan` | **10.2** | dir grew from ~4G; `34100066.csv` alone 8.9G fetched 10:37 today |
| GoogleUpdater crx_cache | 0.7 | new bundle today |
| devin sessions.db + acp-messages | ~1.0 | IDE/cli store growth |
| stock_research_backup dump | 0.2 | owner's backup today (intentional) |
| playwright re-download + misc | ~0.5 | expected cache re-population |

Remaining ~20 GB of the 43 GB delta vs two days ago sits in unreadable
system space (Spotlight rebuild after the panic is the prime suspect but is
**marked UNKNOWN, not assumed** — `.fseventsd` was user-verified at only
884KB; no APFS snapshots; no >100MB deleted-open handles this boot).

## Crash-chain context

10-26 21:55 panic = WindowServer watchdog timeout under memory exhaustion
(3 python jobs ~62GB on 16GB → 42 swapfiles → compressor 100%). Swap itself
lives on the VM volume (19.3G, already reclaimed) and does NOT explain the
Data growth.

## Cleanup summary (DRY RUN — nothing executed)

- Tier 1 trivial regenerable: **~2.4G**
- Tier 2 needs decision: **~12-21G** (claudevm 12G after session ends;
  statcan CSVs gzip → ~8.7G net saving)
- Tier 3 maintenance: ~1-2G
- **Projected total: ~15-25G**, plus whatever the sudo du reveals.

## Recommendations

1. Run `sudo du -xsh /System/Volumes/Data/{,.}* | sort -rh | head -25` once to
   resolve the ~70G UNKNOWN before believing any of this is Spotlight.
2. StatCan CSVs: prefer gzip-in-place (reversible) — verify `macro/master`+
   `out` already carry the derived series.
3. claudevm.bundle: remove only when no claude session holds it.
4. Install `disk_monitor.py` on a schedule later if wanted — script only,
   not installed per spec.
5. Tonight is the EOD hotfix live run — avoid all writes/deletes in
   stock_research until after 22:30.

## Artifacts

`disk_inventory.csv` · `largest_files.csv` · `growth_suspects.csv` ·
`cleanup_candidates.csv` · `system_permission_gaps.md` ·
`disk_cleanup_plan.md` · `disk_monitor.py` · this report.
